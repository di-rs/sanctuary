use chrono::{DateTime, Local};
use std::{
    fmt::Display,
    fs, io,
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
};
use tabular::{Row, Table};

mod owner;
use owner::Owner;
use uzers::{get_group_by_gid, get_user_by_uid};

/// # Errors
/// Returns an error if an operand or its directory contents cannot be read.
pub fn find_files(paths: &[PathBuf], show_hidden: bool) -> io::Result<Vec<PathBuf>> {
    find_files_by(paths, show_hidden, Path::metadata)
}

/// Collects paths for a long listing, treating symbolic links as entries.
///
/// # Errors
/// Returns an error if an operand or its directory contents cannot be read.
pub fn find_long_files(paths: &[PathBuf], show_hidden: bool) -> io::Result<Vec<PathBuf>> {
    find_files_by(paths, show_hidden, Path::symlink_metadata)
}

fn find_files_by(
    paths: &[PathBuf],
    show_hidden: bool,
    metadata: fn(&Path) -> io::Result<fs::Metadata>,
) -> io::Result<Vec<PathBuf>> {
    let mut results = Vec::new();

    for path in paths {
        if metadata(path)?.is_dir() {
            for entry in fs::read_dir(path)? {
                let entry = entry?;
                let path = entry.path();
                let is_hidden = path
                    .file_name()
                    .is_some_and(|filename| filename.to_string_lossy().starts_with('.'));
                if !is_hidden || show_hidden {
                    results.push(path);
                }
            }
        } else {
            results.push(path.to_owned());
        }
    }
    Ok(results)
}

/// # Errors
/// Throws error is unable to read path
pub fn get_formatted_output(paths: &[PathBuf]) -> Result<impl Display, std::io::Error> {
    #[allow(
        clippy::literal_string_with_formatting_args,
        reason = "This is a tabular format string, interpreted by Table::new."
    )]
    let fmt = "{:<}{:<}  {:>}  {:<}  {:<}  {:>}  {:<}  {:<}";
    let mut table = Table::new(fmt);

    for path in paths {
        let metadata = path.symlink_metadata()?;
        let file_type = metadata.file_type();

        let perms = format_mode(metadata.mode());
        let link_count = metadata.nlink();

        let uid = metadata.uid();
        let user = get_user_by_uid(uid).map_or_else(
            || uid.to_string(),
            |u| u.name().to_string_lossy().to_string(),
        );

        let gid = metadata.gid();
        let group = get_group_by_gid(gid).map_or_else(
            || gid.to_string(),
            |u| u.name().to_string_lossy().to_string(),
        );

        let size = metadata.len();
        let modified: DateTime<Local> = DateTime::from(metadata.modified()?);
        let date = modified.format("%b %d %y %H:%M");
        let full_path = format_full_path(path, file_type.is_symlink());

        table.add_row(
            Row::new()
                .with_cell(format_file_type(file_type))
                .with_cell(perms)
                .with_cell(link_count)
                .with_cell(user)
                .with_cell(group)
                .with_cell(size)
                .with_cell(date)
                .with_cell(full_path),
        );
    }

    Ok(table)
}

fn format_file_type(file_type: fs::FileType) -> &'static str {
    if file_type.is_symlink() {
        "l"
    } else if file_type.is_dir() {
        "d"
    } else {
        "-"
    }
}

fn format_mode(mode: u32) -> String {
    format!(
        "{}{}{}",
        permission_triple(mode, Owner::User),
        permission_triple(mode, Owner::Group),
        permission_triple(mode, Owner::Other),
    )
}

fn permission_triple(mode: u32, owner: Owner) -> String {
    let [read, write, execute] = owner.masks();
    format!(
        "{}{}{}",
        if mode & read == 0 { "-" } else { "r" },
        if mode & write == 0 { "-" } else { "w" },
        if mode & execute == 0 { "-" } else { "x" },
    )
}

fn format_full_path(path: &Path, is_symlink: bool) -> String {
    let path_str = path.display();
    if is_symlink {
        path.read_link().map_or_else(
            |_| path_str.to_string(),
            |target| format!("{path_str} -> {}", target.display()),
        )
    } else {
        path_str.to_string()
    }
}

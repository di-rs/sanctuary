use super::buffer::Buffer;
use rustix::fs::OFlags;
use std::{
    fs::{self, File, Metadata},
    io::{self, BufReader, Seek},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
};
mod security;
#[derive(Debug)]
pub enum SaveOutcome {
    Unchanged,
    Saved,
    DurabilityWarning(io::Error),
}

pub(super) struct SavedFile {
    pub(super) path: PathBuf,
    destination: PathBuf,
    file: File,
    text: Buffer,
}

impl SavedFile {
    pub(super) fn matches_destination(&self, destination: &Path) -> bool {
        self.destination == destination
            || fs::canonicalize(&self.path).is_ok_and(|current| current == destination)
            || fs::metadata(destination).is_ok_and(|target| {
                // Canonical paths can retain the caller's spelling on a
                // case-insensitive filesystem.
                self.file
                    .metadata()
                    .is_ok_and(|saved| file_id(&saved) == file_id(&target))
                    || fs::metadata(&self.path)
                        .is_ok_and(|current| file_id(&current) == file_id(&target))
            })
    }

    fn check_identity(&self, destination: &Path, metadata: Option<&Metadata>) -> io::Result<()> {
        let original = self.file.metadata()?;
        if (destination == self.destination
            || fs::canonicalize(&self.path).is_ok_and(|current| current == self.destination))
            && metadata
                .is_some_and(|current| current.is_file() && file_id(current) == file_id(&original))
        {
            return Ok(());
        }
        Err(save_conflict())
    }

    fn check_bytes(&self) -> io::Result<()> {
        // A retained descriptor pins the inode and can also read back a file
        // Kara created by saving over a write-only destination.
        let mut file = &self.file;
        file.rewind()?;
        if self.text.matches_bytes(BufReader::new(file))? {
            return Ok(());
        }
        Err(save_conflict())
    }
}

fn file_id(metadata: &Metadata) -> (u64, u64) {
    (metadata.dev(), metadata.ino())
}

#[derive(PartialEq, Eq)]
struct FileVersion {
    id: (u64, u64),
    size: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}

impl From<&Metadata> for FileVersion {
    fn from(metadata: &Metadata) -> Self {
        Self {
            id: file_id(metadata),
            size: metadata.len(),
            modified: (metadata.mtime(), metadata.mtime_nsec()),
            changed: (metadata.ctime(), metadata.ctime_nsec()),
        }
    }
}

pub(super) fn save_conflict() -> io::Error {
    io::Error::other("File changed on disk. Use :w <filename> to save elsewhere.")
}

pub(super) fn open(path: PathBuf) -> io::Result<(Buffer, SavedFile)> {
    let destination = fs::canonicalize(&path)?;
    let file = File::open(&destination)?;
    let text = Buffer::read(BufReader::new(&file))?;
    let saved = SavedFile {
        path,
        destination,
        file,
        text: text.clone(),
    };
    Ok((text, saved))
}

pub(super) fn resolve_destination(path: &Path) -> io::Result<PathBuf> {
    match fs::canonicalize(path) {
        Ok(path) => Ok(path),
        Err(error) if error.kind() == io::ErrorKind::NotFound => match fs::symlink_metadata(path) {
            Ok(metadata) if metadata.file_type().is_symlink() => Err(io::Error::new(
                io::ErrorKind::NotFound,
                "save destination is a dangling symlink",
            )),
            Ok(_) => Err(error),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let name = path
                    .file_name()
                    .filter(|name| {
                        // Keep a missing path ending in `/` or `/.` from becoming a file.
                        path.as_os_str()
                            .as_encoded_bytes()
                            .rsplit(|byte| *byte == b'/')
                            .next()
                            == Some(name.as_encoded_bytes())
                    })
                    .ok_or(error)?;
                Ok(fs::canonicalize(parent_directory(path))?.join(name))
            }
            Err(error) => Err(error),
        },
        Err(error) => Err(error),
    }
}

fn parent_directory(path: &Path) -> &Path {
    path.parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
}

pub(super) fn save(
    buffer: &Buffer,
    path: PathBuf,
    destination: PathBuf,
    expected: Option<&SavedFile>,
    sync_directory: impl FnOnce(&File) -> io::Result<()>,
) -> io::Result<(SavedFile, SaveOutcome)> {
    let metadata = match fs::symlink_metadata(&destination) {
        Ok(metadata) => Some(metadata),
        Err(error) if error.kind() == io::ErrorKind::NotFound => None,
        Err(error) => return Err(error),
    };
    if let Some(expected) = expected {
        expected.check_identity(&destination, metadata.as_ref())?;
        expected.check_bytes()?;
    }
    let security = match &metadata {
        Some(metadata) => {
            if !metadata.is_file() {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "save destination is not a regular file",
                ));
            }
            if metadata.permissions().readonly() {
                return Err(io::ErrorKind::PermissionDenied.into());
            }
            // Atomic replacement must require write access to the destination,
            // even when the directory permits renaming over it.
            rustix::fs::accessat(
                rustix::fs::CWD,
                &path,
                rustix::fs::Access::WRITE_OK,
                rustix::fs::AtFlags::EACCESS,
            )?;
            let flags = (OFlags::NOFOLLOW | OFlags::NONBLOCK).bits();
            let original = File::options()
                .write(true)
                .custom_flags(i32::try_from(flags).map_err(io::Error::other)?)
                .open(&destination)?;
            if FileVersion::from(metadata) != FileVersion::from(&original.metadata()?) {
                return Err(save_conflict());
            }
            Some(security::Security::read(&destination, &original)?)
        }
        None => None,
    };
    // Opening the directory can fail; do so before committing any changes.
    let parent = parent_directory(&destination);
    let directory = File::open(parent)?;
    let staging = tempfile::tempdir_in(parent)?;
    security::make_private_directory(staging.path())?;
    let mut file = tempfile::NamedTempFile::new_in(staging.path())?;
    security::make_private(file.path(), file.as_file())?;
    buffer.write_to(&mut file)?;
    if let Some(security) = security {
        security.apply(file.path(), file.as_file())?;
    }
    file.as_file().sync_all()?;

    if !resolve_destination(&path).is_ok_and(|current| current == destination) {
        return Err(save_conflict());
    }
    let file = if let Some(metadata) = &metadata {
        if !fs::symlink_metadata(&destination)
            .is_ok_and(|current| FileVersion::from(&current) == FileVersion::from(metadata))
        {
            return Err(save_conflict());
        }
        file.persist(&destination).map_err(|error| error.error)?
    } else {
        file.persist_noclobber(&destination).map_err(|error| {
            if error.error.kind() == io::ErrorKind::AlreadyExists {
                save_conflict()
            } else {
                error.error
            }
        })?
    };
    let saved = SavedFile {
        path,
        destination,
        file,
        text: buffer.clone(),
    };
    let outcome = match sync_directory(&directory) {
        Ok(()) => SaveOutcome::Saved,
        Err(error) => SaveOutcome::DurabilityWarning(error),
    };
    Ok((saved, outcome))
}

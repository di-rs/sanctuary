#[derive(cli_schema::Schema)]
#[schema(name = "true", about = "Exit with status 0; all arguments are ignored")]
struct Cli;

fn main() -> std::process::ExitCode {
    <Cli as cli_schema::Schema>::run(|| {
        cli_log::init("true").finish(i32::from(sanctuary_true::exit_status()))
    })
}

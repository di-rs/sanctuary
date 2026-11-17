#[derive(cli_schema::Schema)]
#[schema(
    name = "false",
    about = "Exit with status 1; all arguments are ignored"
)]
struct Cli;

fn main() -> std::process::ExitCode {
    <Cli as cli_schema::Schema>::run(|| {
        cli_log::init("false").finish(i32::from(sanctuary_false::exit_status()))
    })
}

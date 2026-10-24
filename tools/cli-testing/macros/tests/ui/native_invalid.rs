use cli_testing_macros::cli_test;

#[cli_test("case")]
fn arguments(cx: &TestContext) {}

#[cli_test]
async fn asynchronous(cx: &TestContext) {}

#[cli_test]
fn generic<T>(cx: &TestContext) {}

#[cli_test]
fn missing() {}

#[cli_test]
fn multiple(cx: &TestContext, other: u8) {}

#[cli_test]
fn mutable(cx: &mut TestContext) {}

#[cli_test]
fn owned(cx: TestContext) {}

#[cli_test]
fn wrong(cx: &Context) {}

#[cli_test]
fn pattern(_: &TestContext) {}

#[cli_test]
#[test]
fn duplicate(cx: &TestContext) {}

#[cli_test]
#[should_panic]
fn panic_attribute(cx: &TestContext) {}

#[cli_test]
#[cfg_attr(all(), test)]
fn conditional_test(cx: &TestContext) {}

fn main() {}

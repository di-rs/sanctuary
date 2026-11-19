"""Migrate and verify the owning host's twice-daily cleanup schedules."""

from dataclasses import replace
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode

from boxie.domain.models import SupervisorIdentity
from boxie.temporal.contracts import maintenance_queue
from boxie.temporal.maintenance import Maintenance

_CLEANUP_INTERVAL = 12 * 60 * 60
_POLLING_CATCHUP = timedelta(minutes=1)


def _interval(seconds: int) -> ScheduleSpec:
    return ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=seconds))])


def _schedule(
    queue: str, kind: str, seconds: int, *, catchup_window: timedelta = _POLLING_CATCHUP
) -> Schedule:
    return Schedule(
        action=ScheduleActionStartWorkflow(
            Maintenance.run, kind, id=f"{queue}/{kind}", task_queue=queue
        ),
        spec=_interval(seconds),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP, catchup_window=catchup_window),
    )


def schedule_definitions(identity: SupervisorIdentity) -> dict[str, Schedule]:
    queue = maintenance_queue(identity)
    return {
        f"{queue}/{kind}": _schedule(
            queue, kind, _CLEANUP_INTERVAL, catchup_window=timedelta(seconds=_CLEANUP_INTERVAL)
        )
        for kind in ("artifacts", "retention")
    }


async def _check_schedule(
    client: Client,
    actual: Schedule,
    expected: Schedule,
    *,
    alternate_specs: tuple[ScheduleSpec, ...] = (),
) -> None:
    action, wanted = actual.action, expected.action
    if not isinstance(action, ScheduleActionStartWorkflow) or not isinstance(
        wanted, ScheduleActionStartWorkflow
    ):
        raise RuntimeError("maintenance schedule action differs")
    args = await client.data_converter.decode(list(action.args))
    if (
        actual.state.paused
        or actual.state.limited_actions
        or actual.spec not in (expected.spec, *alternate_specs)
        or (action.workflow, action.id, action.task_queue, args)
        != (wanted.workflow, wanted.id, wanted.task_queue, list(wanted.args))
        or actual.policy != expected.policy
    ):
        raise RuntimeError("maintenance schedule configuration differs")


async def check_schedules(client: Client, identity: SupervisorIdentity) -> None:
    for identifier, expected in schedule_definitions(identity).items():
        actual = (await client.get_schedule_handle(identifier).describe()).schedule
        await _check_schedule(client, actual, expected)


async def ensure_schedules(client: Client, identity: SupervisorIdentity) -> None:
    for identifier, schedule in schedule_definitions(identity).items():
        try:
            await client.create_schedule(identifier, schedule)
        except ScheduleAlreadyRunningError:
            # Only upgrade shipped configurations; reject operator changes.
            async def upgrade(
                update: ScheduleUpdateInput,
                expected: Schedule = schedule,
            ) -> ScheduleUpdate | None:
                actual = update.description.schedule
                if actual.spec == expected.spec:
                    await _check_schedule(client, actual, expected)
                    return None
                legacy = replace(
                    expected,
                    spec=_interval(30),
                    policy=replace(expected.policy, catchup_window=_POLLING_CATCHUP),
                )
                await _check_schedule(client, actual, legacy, alternate_specs=(_interval(300),))
                actual.spec = expected.spec
                actual.policy = expected.policy
                return ScheduleUpdate(schedule=actual)

            await client.get_schedule_handle(identifier).update(upgrade)
    queue = maintenance_queue(identity)
    for kind, seconds, alternate_seconds in (("commands", 5, 15), ("journal", 30, 60)):
        identifier = f"{queue}/{kind}"
        handle = client.get_schedule_handle(identifier)
        try:
            actual = (await handle.describe()).schedule
        except RPCError as error:
            if error.status == RPCStatusCode.NOT_FOUND:
                continue
            raise
        await _check_schedule(
            client,
            actual,
            _schedule(queue, kind, seconds),
            alternate_specs=(_interval(alternate_seconds),),
        )
        await handle.delete()
    await check_schedules(client, identity)

"""Prepare one route-driven continuation of the completed credit ECO.

Remaining worst paths are pad-border decode to window BRAM, dominated by
interconnect. This runner asks the router to revisit timing-critical routes,
then runs physical cleanup. It does not change the ECO or RTL function.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)

def create(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

helper = (HERE / 'postroute_eco/prepare.py').read_text(encoding='utf-8')
helper = replace_once(helper, "baseline.parent.name != 'postroute200_v1_nominal000_20261003_try2'",
                       "baseline.parent.name != 'postroute200_v1_credit_eco030_20261003_try1'")
helper = replace_once(helper, "ECO is reviewed only for the exact retained nominal finish",
                       "Route continuation requires the exact retained credit ECO")
helper = replace_once(helper, "baseline.parent / 'input/baseline_reports/launch_source_manifest.json'",
                       "baseline.parent / 'input/launch_source_manifest.json'")
create(HERE / 'postroute_route/prepare.py', '# Route-driven continuation, no further logic changes.\n' + helper)
runner = (ROOT / 'experiments/timing_200_20260926/postroute_finish/finish.tcl').read_text(encoding='utf-8')
anchor = '        phys_opt_design -directive AggressiveExplore'
runner = replace_once(runner, anchor, '''        # Installed route_design help: AggressiveExplore revisits critical
        # routes; tns_cleanup addresses other negative endpoints. No preserve
        # flag here because existing critical routes must be eligible to change.
        route_design -directive AggressiveExplore -tns_cleanup
        update_timing
        finish_snapshot "$finish_stage/reports/after_route_pressure" $finish_clock
''' + anchor)
create(HERE / 'postroute_route/finish.tcl', '# Credit ECO route-driven finish; final acceptance uses UU=0 only.\n' + runner)
print('ROUTE_DRIVEN_CONTINUATION_RUNNER_PREPARED')

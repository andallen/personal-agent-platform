from pathlib import Path

from cc_mobile.detectors import (
    PermissionPromptDetector,
    PlanApprovalDetector,
)

FIX = Path(__file__).parent / "fixtures" / "pane"


# Real fixture
def test_edit_permission_detected_from_real_fixture():
    text = (FIX / "permission_edit.txt").read_text()
    det = PermissionPromptDetector()
    ev = det.detect(text)
    assert ev is not None
    assert ev.kind == "edit"
    # The target line names the file
    assert "research-test.txt" in ev.target


# Synthesized bash prompt (real fixture lacks one due to allow-list)
def test_bash_permission_detected_from_synthesized():
    text = """\
❯ list /tmp using bash

● Bash(ls -la /tmp)

 Do you want to run this command?
 ❯ 1. Yes
   2. Yes, allow all bash commands during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
"""
    det = PermissionPromptDetector()
    ev = det.detect(text)
    assert ev is not None
    assert ev.kind == "bash"
    # The question says "run this command" — the specific command isn't in the question line
    assert "run" in ev.target or "bash" in ev.target.lower() or "command" in ev.target


def test_no_permission_in_normal_pane():
    text = "$ echo hello\nhello\n$ "
    det = PermissionPromptDetector()
    assert det.detect(text) is None


# Synthesized plan-approval (real fixture didn't capture the gate)
def test_plan_approval_detected_from_synthesized():
    text = """\
● Here is the plan:

  1. First, create the script.
  2. Then, test it.
  3. Finally, document it.

 Ready to code?
 ❯ 1. Yes, and auto-approve subsequent edits
   2. Yes, and ask for approval again
   3. No, keep working in plan mode
"""
    det = PlanApprovalDetector()
    ev = det.detect(text)
    assert ev is not None
    assert ev.kind == "plan_approval"


def test_plan_approval_none_when_just_in_plan_mode():
    text = "❯ \n\n⏸ plan mode on (shift+tab to cycle)\n"
    det = PlanApprovalDetector()
    assert det.detect(text) is None

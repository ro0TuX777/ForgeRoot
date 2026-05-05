# ONBOARDING_LEAD_MANUAL

## Step 4: VERIFY (Azul Verdict)

Run verification using the wrapper:

```bash
cd /Users/vinsoncornejo/ForgedRoot
source scripts/setup_env.sh
./scripts/azul-verify --diff hack.patch --summary "Testing the Subprocess Guard with a malicious rm command"
```

Expected governed outcome (successful security governance):

- `Azul Verdict: REJECT [critical]`
- `XP: 0`
- Alert contains: `Guard Predicate Violation: external.subprocess.check_call ... args[0] 'rm' ... kwargs.get('shell') expected False but got True`

Reference example from validated run:

- Ticket: `azul-d367d35c`
- Verdict reason: `Guard Predicate Violation: external.subprocess.check_call at src/app/__init__.py:3 -> args[0] 'rm' not in ['ls', 'git status', 'whoami']; kwargs.get('shell') expected False but got True`

### The Power of the Reason

If Azul returns a REJECT, the system is working. If the `verdict_reason` is a Guard Predicate Violation, the human architect has done their job. The developer must now align with the Action Catalog. Do not call a meeting to "discuss" security. The rule is the rule.

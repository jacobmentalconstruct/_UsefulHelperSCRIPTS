def resolve_template(template: str, state: dict) -> str:
    """
    Minimal {{state.path.to.key}} templating.
    Only supports read access, no function calls.
    """
    out = template

    # very small & safe on purpose
    # pattern scanning without regex to keep it obvious
    while True:
        start = out.find("{{")
        if start == -1:
            break
        end = out.find("}}", start)
        if end == -1:
            break
        expr = out[start+2:end].strip()

        val = ""
        if expr.startswith("state."):
            path = expr[len("state."):].split(".")
            cur = state
            ok = True
            for p in path:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    ok = False
                    break
            if ok:
                val = cur if isinstance(cur, str) else str(cur)

        out = out[:start] + val + out[end+2:]
    return out

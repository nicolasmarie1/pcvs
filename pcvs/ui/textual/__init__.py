try:
    # flake8: noqa: F401
    import textual

    TEXTUAL_AVAIL = True
except Exception:
    TEXTUAL_AVAIL = False

"""USPTO trademark status code lookup.

Codes are stable and documented at https://tsdr.uspto.gov/documentation/.
We bucket into broad lifecycle stages because that's what readers actually
want to know ("is this mostly registered, examined, or abandoned?") — the
30+ specific codes are noise in a chart.
"""


def bucket(code: str | int | None) -> str:
    """Map a USPTO trademark status code to a lifecycle bucket."""
    if code is None or code == "":
        return "Unknown"
    try:
        c = int(code)
    except (ValueError, TypeError):
        return "Unknown"

    if c in {700, 701, 702, 706, 707, 780}:
        return "Registered"
    if c in {704, 705, 708, 710, 711, 712, 714, 715, 716, 717, 718,
             720, 721, 722, 723, 724, 725}:
        return "Cancelled"
    if 800 <= c <= 899:
        return "Abandoned"
    if 730 <= c <= 799:
        # 730-749 = NOA/SOU; 750-799 = post-publication processing
        return "Allowed / processing"
    if c in {680, 681, 688, 692, 709}:
        return "Suspended"
    if 600 <= c <= 699:
        return "Under examination"
    if 400 <= c <= 499:
        return "Filed (priority)"
    return f"Other ({c})"

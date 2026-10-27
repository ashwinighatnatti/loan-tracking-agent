import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from nameparser import HumanName
from rapidfuzz import fuzz

#=================================================================================================
# MATCH INSURANCE NAMES AND ADDRESSES
#=================================================================================================

def normalize_suffix(suffix: str) -> str:
    """Standardize common suffixes, Roman numerals, and generations."""
    s = suffix.lower().replace(".", "").strip()
    suffix_map = {
        "jr": "jr", "junior": "jr",
        "sr": "sr", "senior": "sr",
        "i": "1", "1st": "1", "first": "1",
        "ii": "2", "2nd": "2", "second": "2",
        "iii": "3", "3rd": "3", "third": "3",
        "iv": "4", "4th": "4", "fourth": "4",
        "v": "5", "5th": "5", "fifth": "5"
    }
    return suffix_map.get(s, s)

# Common nickname groups; any two names in the same group are treated as the same first name.
NICKNAME_GROUPS = [
    {"christopher", "chris", "kit"},
    {"terrance", "terrence", "terry"},
    {"susan", "sue", "susie", "suzanne"},
    {"walter", "wal", "walt", "wally"},
    {"richard", "rich", "rick", "richy", "dick", "rishi", "richardson"},
    {"robert", "rob", "bob", "bobby", "robbie"},
    {"william", "will", "bill", "billy", "liam"},
    {"james", "jim", "jimmy", "jamie"},
    {"john", "jack", "johnny", "jon"},
    {"margaret", "maggie", "meg", "peggy"},
    {"elizabeth", "liz", "beth", "betty", "eliza"},
    {"katherine", "catherine", "kathy", "kate", "katie", "cathy"},
    {"edward", "ed", "eddie", "ted", "ned"},
    {"thomas", "tom", "tommy"},
    {"michael", "mike", "mick"},
    {"joseph", "joe", "joey"},
    {"anthony", "tony"},
    {"patricia", "pat", "patty", "trish"},
    {"francis", "frank", "fran"},
    {"barbara", "barb", "barbie"},
    {"deborah", "debra", "deb", "debbie"},
]
NICKNAMES = {name: i for i, group in enumerate(NICKNAME_GROUPS) for name in group}

BORROWER_LABEL_RE = re.compile(r"\b(?:primary|co)\s*-?\s*borrower\s*[-:]?", re.IGNORECASE)
ESTATE_TRUST_RE = re.compile(r"\bestate\s+of\b|\b(?:revocable\s+|living\s+|family\s+)*trust\b", re.IGNORECASE)
PERSON_SEPARATOR_RE = re.compile(r"\s*\n\s*|\s+(?:and|&)\s+", re.IGNORECASE)
INITIAL_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]\.?(?![A-Za-z])")

@dataclass
class Person:
    first: str
    lasts: set[str]  # last name, plus middle + last to cover multi-word surnames
    suffix: str


def _parse_person(text: str) -> Person:
    # Drop single-letter initials unless that would leave fewer than two name words
    without_initials = INITIAL_RE.sub(" ", text)
    if len(re.findall(r"[A-Za-z]{2,}", without_initials)) >= 2:
        text = without_initials
    n = HumanName(" ".join(text.split()))
    first, middle, last, suffix = n.first.lower(), n.middle.lower(), n.last.lower(), n.suffix
    # "SAINT CLAIR, JUNIOR" parses Junior as a suffix with no first name
    if not first and suffix:
        first, suffix = suffix.lower(), ""
    lasts = {l for l in (last, f"{middle} {last}".strip() if last else "") if l}
    return Person(first, lasts, normalize_suffix(suffix))


def _split_people(name: str) -> list[Person]:
    """Splits a field holding one or more borrowers into individual people."""
    name = ESTATE_TRUST_RE.sub(" ", BORROWER_LABEL_RE.sub(" ", name.replace("\r", "")))
    people = [_parse_person(part) for part in PERSON_SEPARATOR_RE.split(name) if part.strip(" ,-")]
    # "ASHFORD, FRANK and DIANE" / "Terry And Sue Brantley": a lone first name shares the other's last name
    shared = next((p.lasts for p in people if p.lasts), set())
    for p in people:
        if not p.lasts and len(people) > 1:
            p.lasts = set(shared)
    return people


def _first_name_score(a: str, b: str) -> float:
    if not a or not b:
        return 0
    if a in NICKNAMES and NICKNAMES.get(a) == NICKNAMES.get(b):
        return 100
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 3 and longer.startswith(shorter):
        return 100
    return fuzz.ratio(a, b)


def _last_name_score(lasts: set[str], other: str) -> float:
    return max((fuzz.ratio(l, other) for l in lasts), default=0)


def match_person(p1: Person, p2: Person, fuzzy_threshold: int) -> bool:
    
    # CRITICAL FOR INSURANCE: If both names specify a suffix and they differ (e.g., Jr vs Sr, II vs III),
    # they are distinct individuals.
    if p1.suffix and p2.suffix and p1.suffix != p2.suffix:
        return False

    # Only a single name on one side (e.g. "LEA TRUST"): accept if it matches either name of the other
    for a, b in ((p1, p2), (p2, p1)):
        if not a.lasts:
            return max(_first_name_score(a.first, b.first), _last_name_score(b.lasts, a.first)) >= fuzzy_threshold

    # Score 1: Direct order (First A == First B and Last A == Last B)
    score_direct = (_first_name_score(p1.first, p2.first)
                    + max(_last_name_score(p1.lasts, l) for l in p2.lasts)) / 2
    
    # Score 2: Swapped order (First A == Last B and Last A == First B)
    # (first names may land in the last-name slot, so allow nicknames there too: "HOLLOWAY CHRIS")
    score_swapped = (max(_first_name_score(p1.first, l) for l in p2.lasts)
                     + max(_first_name_score(p2.first, l) for l in p1.lasts)) / 2

    return max(score_direct, score_swapped) >= fuzzy_threshold


def match_insurance_names(name1: str, name2: str, fuzzy_threshold: int = 85) -> bool:
    """
    Compares two names for insurance document processing.

    Rules:
    1. Handles First/Last name swaps (e.g., "John Smith" vs "Smith John").
    2. Ignores middle names/initials.
    3. Strictly enforces generational suffix matches (Jr/Sr, Roman Numerals) to avoid
       confusing father/son or generational family members.
    4. Performs fuzzy comparison on first and last names to handle OCR errors/typos.
    5. Splits fields with multiple borrowers ("Primary Borrower - ... / Co-Borrower - ...",
       "X and Y") and matches if any person on one side matches any person on the other.
    6. Ignores "Estate of" and "Trust" wording.
    7. Accepts common nicknames and shortened first names (Chris / Christopher).

    Multiple borrowers: it strips "Primary Borrower -" and "Co-Borrower -", then splits the field on line breaks, "and" and "&". Two fields match if any person in one matches any person in the other.
    Shared last name: a part that is only a first name takes the other person's last name, so "ASHFORD, FRANK and DIANE" becomes Diane Ashford and "Terry And Sue Brantley" becomes Terry Brantley.
    Estate and trust wording: "Estate of" and "Trust" are removed before comparing, including "Revocable Trust", "Living Trust" and "Family Trust".
    Nicknames: there's a list of about 20 nickname groups (Chris/Christopher, Terry/Terrance, Sue/Susan, Walt/Walter, and so on). A short first name that starts a longer one (Wal/Walter) also counts as a match. Nicknames are checked even when names are in last-first order without a comma, as in "HOLLOWAY CHRIS".
    Multi-word surnames: "VANDERMERE HOLCOMB" matches whether it is read as middle plus last name or as one last name.
    "Junior" as a first name: in "SAINT CLAIR, JUNIOR", "Junior" is treated as the first name rather than a Jr. suffix.
    Initials: single letters such as "L" in "ARNOLD L MARSH" are ignored, as long as at least two name words remain.

    These rules make matching looser, so a few cases could now pass that shouldn't:

    Single name: if one side has only one name ("LEA TRUST" leaves just "LEA"), it matches when that name equals either the first or last name on the other side.
    Short-name prefix: any name of three or more letters that starts a longer one counts as a match, so "Dan" matches "Daniel" but would also match "Danielle".
    Short nickname list: names not in the list still fall back to fuzzy spelling.
    """
    people1, people2 = _split_people(name1), _split_people(name2)
    return any(match_person(a, b, fuzzy_threshold) for a in people1 for b in people2)


#=====================================================
#  INSURANCE NAMES TEST DATA
#=====================================================
INSURANCE_NAMES_TEST_DATA = """
"FRANK R ASHFORD
DIANE A ASHFORD"|"ASHFORD, FRANK and DIANE"|Yes
James A Hargrove|"HARGROVE, PRISCILLA"|No
"Primary Borrower - Roger Sanderford
Co-Borrower -Ruth Sanderford"|"SANDERFORD, ROGER AND SANDERFORD, RUTH"|Yes
Francis Edward Delacroix|"DELACROIX,FRANCIS"|Yes
KAREN J WELLER|"Wellick, Jane"|No
"Primary Borrower - BARBARA M CRANMER
Co-Borrower -JAMES C CRANMER"|"CRANMER, JAMES"|Yes
 WAL VANDERMERE HOLCOMB|"VANDERMERE HOLCOMB,WALTER"|Yes
Frank Smith Jr|Frank Smith|Yes
Frank Smith Jr|Frank Smith Sr.|No
LINDA S BRIGGS|"BRIGGS, DOUGLAS"|No
LINDA S BRIGGS|"BRIGGS, LINDA"|Yes
JUNIOR SAINT CLAIR|"SAINT CLAIR, JUNIOR "|Yes
CHRISTOPHER W HOLLOWAY|HOLLOWAY CHRIS|Yes
MANUEL F MARLOWE|"MARLOWE JR, MANUEL"|Yes
"Primary Borrower - TERRANCE BRANTLEY
Co-Borrower - SUSAN BRANTLEY"|Terry And Sue Brantley|Yes
KEITH L FRAZIER|Teresa Frazier|No
ARNOLD L MARSH|Estate of Marsh Arnold L|Yes
 DARRIN ELLIS III| DARRIN ELLIS|Yes
 DARRIN ELLIS III| DARRIN ELLIS II|No
 DARRIN ELLIS|"ELLIS, BRENT"|No
LEA J. LANGLEY TRUST|ESTATE OF LEA LANGLEY|Yes
LEA  TRUST|LEA J. LANGLEY|Yes
WILLIAM CARLTON|BILL CARLTON|Yes
CHRISTOPHER JAMESON| CHRIS JAMESON|Yes
BHOMINAIDU RAMESH|RAMESH NAIDU|Yes
"""

def _run_insurance_names_test(data: str = INSURANCE_NAMES_TEST_DATA) -> None:
    """
    Reads pipe-delimited lines of name1|name2|expected (Yes/No), runs
    match_insurance_names on each pair and reports whether the result agrees with expected.
    """
    print("="*60)
    print("RUN INSURANCE NAMES TEST")
    print("="*60)
        
    total = passed = 0
    for row in csv.reader(io.StringIO(data), delimiter="|"):
        if len(row) < 3 or not row[0].strip():
            continue
        name1, name2, expected = row[0].strip(), row[1].strip(), row[2].strip().lower() == "yes"
        actual = match_insurance_names(name1, name2)
        total += 1
        passed += actual == expected
        status = "PASS" if actual == expected else "FAIL"
        print(f"{status}: {name1!r} vs {name2!r} -> expected {expected}, got {actual}")
    print(f"\n{passed}/{total} matched expected results")

#=================================================================================================
# VERIFY 60 - 120 DAY THRESHOLD FROM A DATE
#=================================================================================================

DATE_FORMAT = "%m/%d/%Y"


def _to_date(value: str | date) -> date:
    """Accepts a date/datetime or an mm/dd/yyyy string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.strptime(value.strip(), DATE_FORMAT)


def within_60_120_threshold(effective_date: str | date,
                                processing_date: str | date | None = None,
                                days_before: int = 60,
                                days_after: int = 120) -> bool:
    """
    60-120 day threshold rule.

    Compares the policy Effective-Date (mm/dd/yyyy) with the Processing-Date
    (defaults to today's date). The rule matches when the Effective-Date is no
    more than 60 days before and no more than 120 days after the Processing-Date
    (both bounds inclusive). It does NOT match when the Effective-Date is beyond those bounds.
    """
    effective = _to_date(effective_date)
    processing = _to_date(processing_date) if processing_date is not None else date.today()
    return processing - timedelta(days=days_before) <= effective <= processing + timedelta(days=days_after)



# effective_date|processing_date|expected (Yes/No)
EFFECTIVE_DATE_TEST_DATA = """
10/18/2026|10/18/2026|Yes
08/19/2026|10/18/2026|Yes
08/18/2026|10/18/2026|No
02/15/2027|10/18/2026|Yes
02/16/2027|10/18/2026|No
01/01/2026|10/18/2026|No
12/31/2026|10/18/2026|Yes
"""

def _run_within_60_120_threshold_test(data: str = EFFECTIVE_DATE_TEST_DATA) -> None:
    """Runs match_effective_date_window on each effective|processing|expected row."""

    print("="*60)
    print("RUN IS 60-120 THRESHOLD TEST")
    print("="*60)

    total = passed = 0
    for row in csv.reader(io.StringIO(data), delimiter="|"):
        if len(row) < 3 or not row[0].strip():
            continue
        effective, processing, expected = row[0].strip(), row[1].strip(), row[2].strip().lower() == "yes"
        actual = within_60_120_threshold(effective, processing)
        total += 1
        passed += actual == expected
        status = "PASS" if actual == expected else "FAIL"
        print(f"{status}: effective {effective} vs processing {processing} -> expected {expected}, got {actual}")
    print(f"\n{passed}/{total} matched expected results")


#=================================================================================================
# Policy Terms Comparision and handling 
#=================================================================================================

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from enum import Enum

@dataclass
class Term:
    start: date
    end: date

    class Relation(str, Enum):
        EQUAL = "equal"         # same start and end dates
        PAST = "past"           # term1 ends on/before term2 starts
        FUTURE = "future"       # term1 starts on/after term2 ends
        REXTEND = "r-extend"  # the terms overlap to the right
        LEXTEND = "l-extend"  # the terms overlap to the left
        CONTAINED = "contained" # term2 contained entirely within term1
        SUPERSEDE = "supersede" # term1 contained entirely within term2

    TERM_DATE_FORMAT: str = "%m/%d/%Y"

    def _to_date(self, value: str | date) -> date:
        """Accepts a date/datetime or an mm/dd/yyyy string."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.strptime(value.strip(), Term.TERM_DATE_FORMAT)

    def __post_init__(self):
        self.start = self._to_date(self.start)
        self.end = self._to_date(self.end)
        if self.start > self.end:
            raise ValueError(f"Term start {self.start} is after its end {self.end}")

    # A term is "less than" another when it is entirely before it. Terms that only
    # touch (one ends the day the next starts, as with a policy renewal) don't overlap.
    def __lt__(self, other: "Term") -> bool:
        return self.end <= other.start

    def __gt__(self, other: "Term") -> bool:
        return self.start >= other.end

    def __str__(self):
        return f"[{self.start.strftime(self.TERM_DATE_FORMAT)},{self.end.strftime(self.TERM_DATE_FORMAT)}]"

    # == comes from @dataclass: equal when both start and end dates match.
    # It is checked first, since a one-day term would otherwise also count as < itself.
    def compare(self, other: "Term") -> Term.Relation:
        if self == other:
            return Term.Relation.EQUAL
        if self < other:
            return Term.Relation.PAST
        if self > other:
            return Term.Relation.FUTURE
        if other.start >= self.start and other.end <= self.end:
            return Term.Relation.CONTAINED
        if self.start > other.start and self.end < other.end:
            return Term.Relation.SUPERSEDE
        return Term.Relation.REXTEND if other.end > self.end else Term.Relation.LEXTEND

    """
    - Renewal Term is present term + 1 year
    - Returns the renewal term from the present term
    - Automatically drops Feb 29 to Feb 28 in non-leap years without crashing.
    """
    def get_renewal_term(self) -> Term:
        return Term(self.start + relativedelta(years=1), self.end + relativedelta(years=1))

    def is_renewal_term(self, term: Term) -> bool:
        return self.get_renewal_term().compare(term) == Term.Relation.EQUAL


#========================
# Term Test
#========================

def compare_terms(term1: Term, term2: Term) -> Term.Relation:
    """EQUAL if term1 == term2, PAST if term1 < term2, FUTURE if term1 > term2, otherwise OVERLAP (they overlap)."""
    return term1.compare(term2)



# term1 start, term1 end, term2 start, term2 end, expected result
# Expected is past / future / equal / overlap, or "error" when the line should be rejected.
# Lines starting with # are skipped.
COMPARE_TERMS = """
# --- past: term1 ends on/before term2 starts ---
4/1/2025, 3/31/2026, 4/1/2026 , 3/31/2027, past
# renewal: term1 ends the day term2 starts
9/13/2025, 9/13/2026, 9/13/2026, 9/13/2027, past
1/1/2020, 12/31/2020, 1/1/2025, 12/31/2025, past
1/1/2025, 12/31/2025, 1/1/2026, 12/31/2026, past
# one-day term1 on term2's start date
3/1/2025, 3/1/2025, 3/1/2025, 3/31/2025, past
# leap day start
2/29/2024, 2/28/2025, 3/1/2025, 2/28/2026, past

# --- future: term1 starts on/after term2 ends ---
4/1/2026, 3/31/2027, 4/1/2025, 3/31/2026, future
# renewal: term1 starts the day term2 ends
9/13/2026, 9/13/2027, 9/13/2025, 9/13/2026, future
1/1/2030, 12/31/2030, 1/1/2025, 12/31/2025, future
# one-day term1 on term2's end date
3/31/2025, 3/31/2025, 3/1/2025, 3/31/2025, future

# --- equal: same start and end ---
4/1/2025, 3/31/2026, 4/1/2025, 3/31/2026, equal
# leading zeros are the same dates
04/01/2025, 03/31/2026, 4/1/2025, 3/31/2026, equal
# one-day terms
6/15/2025, 6/15/2025, 6/15/2025, 6/15/2025, equal
# case-insensitive expected value
4/1/2025, 3/31/2026, 4/1/2025, 3/31/2026, EQUAL

# --- overlap: the terms overlap ---
# term1 starts first
1/1/2025, 12/31/2025, 7/1/2025, 6/30/2026, r-extend
# term2 starts first
7/1/2025, 6/30/2026, 1/1/2025, 12/31/2025, l-extend
# term1 inside term2
3/1/2025, 6/30/2025, 1/1/2025, 12/31/2025, supersede
# term1 contains term2
1/1/2025, 12/31/2025, 3/1/2025, 6/30/2025, contained
# same start, different end
1/1/2025, 6/30/2025, 1/1/2025, 12/31/2025, r-extend
# same end, different start
6/1/2025, 12/31/2025, 1/1/2025, 12/31/2025, l-extend
# overlap by a single day
1/1/2025, 6/2/2025, 6/1/2025, 12/31/2025, r-extend
# one-day term1 inside term2
6/15/2025, 6/15/2025, 1/1/2025, 12/31/2025, supersede
# off by one day from equal
4/1/2025, 3/31/2026, 4/2/2025, 3/31/2026, contained

# --- error: invalid input is rejected ---
# term1 ends before it starts
3/31/2026, 4/1/2025, 4/1/2025, 3/31/2026, error
# no such date
2/30/2025, 3/31/2026, 4/1/2025, 3/31/2026, error
# 2025 is not a leap year
2/29/2025, 3/31/2026, 4/1/2025, 3/31/2026, error
# wrong date format
2025-04-01, 3/31/2026, 4/1/2025, 3/31/2026, error
# too few / too many values
4/1/2025, 3/31/2026, 4/1/2026, error
4/1/2025, 3/31/2026, 4/1/2026, 3/31/2027, 3/31/2028, error
"""


def _run_compare_terms_test() -> int:
    """Compare the two terms on each COMPARE_TERMS line with the expected result in its 5th value.
    Returns the number of lines that failed or could not be checked."""

    print("="*60)
    print("RUN COMPARE TERMS TEST")
    print("="*60)

    passed = failed = 0
    for line_no, line in enumerate(COMPARE_TERMS.strip().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        values = [v.strip() for v in line.split(",")]
        # A last value of "error" means the line is expected to be rejected.
        expect_error = values[-1].lower() == "error"
        try:
            if len(values) != 5:
                raise ValueError(f"expected 5 values, got {len(values)}")
            term1, term2 = Term(values[0], values[1]), Term(values[2], values[3])
            expected = None if expect_error else Term.Relation(values[4].lower())
        except ValueError as exc:
            if expect_error:
                passed += 1
                print(f"PASS  line {line_no}: {line.strip()}  ->  rejected: {exc}")
            else:
                failed += 1
                print(f"ERROR line {line_no}: {line.strip()}  ->  {exc}")
            continue

        actual = compare_terms(term1, term2)
        if expect_error:
            failed += 1
            print(f"FAIL  line {line_no}: {line.strip()}  ->  expected error, got {actual.value}")
        elif actual == expected:
            passed += 1
            print(f"PASS  line {line_no}: {line.strip()}")
        else:
            failed += 1
            print(f"FAIL  line {line_no}: {line.strip()}  ->  expected {expected.value}, got {actual.value}")

    print(f"\n{passed} passed, {failed} failed")
    return failed


#=================================================================================================
# RUN TESTS
#=================================================================================================

if __name__ == "__main__":
    _run_insurance_names_test()
    _run_within_60_120_threshold_test()
    _run_compare_terms_test()

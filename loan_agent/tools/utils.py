import random
import secrets
from typing import Optional

from datetime import date, datetime
from pathlib import Path

#============= Generate Uniq Execution Id

def generate_uniq_id(seed) -> str:
    return  f"{date.today():%Y%m%d}-{seed}-{ ''.join(secrets.choice('abcdefghijkmnpqrstuvwxyz23456789') for _ in range(6)) }-{random.randint(1,9)}"

def _check_generate_uniq_id(num):
    print (generate_uniq_id("0000"))


#============= Create a folder path on disk

def make_path(root: str, dirs: str):
    """
    input: 91241191-0000-c3btr7-2
    """
    path = Path(root + "/" + dirs.replace("-","/"))
    path.mkdir(parents=True, exist_ok=True)

    return

def _check_make_path():

    make_path(str(Path.cwd()),"a-b-c-d")
    return

#============= Compare two names safely

def safe_compare(str1: str, str2: str) -> bool:
    """
        safe_comapre("Cedar   Mutual Co.", "  Cedar Mutual Co.")
    """
    return "".join(str1.split()).casefold() == "".join(str2.split()).casefold()


#============= Compare two addresses safely
def normalize_address(address: str) -> str:
    """
        same_address("21 BIRCHWOOD CT BAYONNE, NJ 07002", "21 birchwood ct, Bayonne NJ 07002") -> True
    """
    return "".join(ch for ch in (address or "") if ch.isalnum()).casefold()

def same_address(addr1: str, addr2: str) -> bool:
    return normalize_address(addr1) == normalize_address(addr2)


#============= Policy Number

LENDER_PLACED_SUFFIXES = ("MLR", "FLR", "ALR")

"""
    normalize_policy_number(" abc-123 #mlr ") -> "ABC123MLR"
"""
def normalize_policy_number(policy_number: str) -> str:
    return "".join(ch for ch in (policy_number or "") if ch.isalnum()).upper()

"""
    has_lender_placed_suffix("ABC-123 MLR") -> True
"""
def has_lender_placed_suffix(policy_number: str) -> bool:
    return normalize_policy_number(policy_number).endswith(LENDER_PLACED_SUFFIXES)

#============= Date difference

def days_between(date_str1: str, date_str2: str, date_format: str = "%m/%d/%Y") -> Optional[int]:
    """
    Computes the absolute difference in days between two date strings safely.
    
    Args:
        date_str1 (str): First date string.
        date_str2 (str): Second date string.
        date_format (str): The format expected for the strings (default: 'MM/DD/YYYY').
        
    Returns:
        Optional[int]: The difference in days, or -1 if parsing fails.
    """
    try:
        date1 = datetime.strptime(date_str1, date_format)
        date2 = datetime.strptime(date_str2, date_format)
        return abs((date2 - date1).days)
    except ValueError as e:
        # Handle invalid date formats, typos, or impossible dates (e.g., 02/30/2026)
        print(f"Warning: fn:days_between. Could not parse dates. Details: {e}")
        return -1


#============= Last token of a string

def last_token(text: str) -> str:
    """
        last_token("1 of 2") -> "2"
        last_token("  ") -> ""
    """
    tokens = (text or "").split()
    return tokens[-1] if tokens else ""


#==========================================
#  Tests
#==========================================

if __name__ == "__main__":
    # _check_generate_uniq_id("0000")
    # _check_make_path()
    print(safe_compare("Cedar   Mutual Co.", "  Cedar Mutual Co."))
    print(normalize_policy_number(" abc-123 #mlr "), has_lender_placed_suffix("ABC-123 # flr"), has_lender_placed_suffix("ABC-123"))

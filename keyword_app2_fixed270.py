# -*- coding: utf-8 -*-
"""
Keyword Risk Analyzer (FIXED270 - before auxiliary analysis)
- Based on v97
- NEW: 드롭다운 목록을 JSON 파일로 영구 저장하여 재부팅 후에도 유지
- KEEP: 모든 기존 기능 유지 (조회 수 카운팅, 리포트, 최근 7일 초기화 등)
"""
from __future__ import annotations
from typing import List, Tuple, Set, Optional
import pandas as pd
from matching_engine import (
    DB_COLS, Match2, MatchingConfig, MATCH_MODES,
    _KO_SUFFIX_WHITELIST, _DEFAULT_IGNORED_SPECIAL_SYMBOLS,
    find_matches as _engine_find_matches,
    find_matches_nlp as _engine_find_matches_nlp,
)
import streamlit as st

# Global tooltip data for highlight preview (kept separate from preview HTML)
HIGHLIGHT_TOOLTIP_MAP: dict = {}


# --- Custom CSS for larger '텍스트 분석하기' button ---
import streamlit as st
st.markdown(
    """
<style>
div.stButton > button {
    height: 35px !important;
    padding: 12px 20px !important;
    font-size: 1rem !important;
}
</style>
""",
    unsafe_allow_html=True
)
# --- End Custom CSS ---
import streamlit.components.v1 as components
import html, io, re, zipfile, os, json
import hashlib
import time
from uuid import uuid4
from dataclasses import asdict
from xml.etree import ElementTree as ET
from pathlib import Path
from app_config import configure, cloud_enabled
from repository import SupabaseRepository, StorageError, ConflictError
from service import load_matching_config, match_text

try:
    configure(dict(st.secrets))
except FileNotFoundError:
    configure()


def _require_admin():
    if not st.session_state.get('is_admin', False):
        st.error('관리자만 데이터를 변경할 수 있습니다.')
        st.stop()

st.markdown("""
<style>
div.streamlit-expander {
    margin-bottom: 0rem !important;
}
</style>
""", unsafe_allow_html=True)


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def now_kst():
    return datetime.now(ZoneInfo('Asia/Seoul')).replace(tzinfo=None)

# Streamlit cache alias (지원 버전 차이 대응)
try:
    _cache_data = st.cache_data
except AttributeError:  # Streamlit < 1.18
    _cache_data = st.cache

# Constants
MAX_HIGHLIGHT_HEIGHT = 600  # px
DEFAULT_HEADER_ROW = 1
CONFIG_FILE_NAME = "dropdown_config.json"  # 드롭다운 설정 저장 파일

st.markdown(
    """
    <style>
    /* 기본 mark 스타일: 배경색은 지정하지 않고, 텍스트 색상만 지정 */
    mark {
        color: #000 !important;
    }
    /* Compact layout ONLY for highlight quick-select area */
    .quick-select-block div[data-testid="stHorizontalBlock"] {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    .quick-select-block div[data-testid="column"] {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    .quick-select-block [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }
    .quick-select-block div.stButton > button {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        min-height: 1.1rem !important;
    }
</style>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# XLSX reader without openpyxl (first sheet only, basic types)
# -----------------------------
def _xlsx_list_worksheets(zf: zipfile.ZipFile) -> List[str]:
    paths = [p for p in zf.namelist() if p.startswith("xl/worksheets/") and p.endswith(".xml")]
    return sorted(paths) if paths else []

def _xlsx_load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        with zf.open("xl/sharedStrings.xml") as fp:
            tree = ET.parse(fp)
        root = tree.getroot()
        ns = {"a": root.tag.split("}")[0].strip("{")}
        strings = []
        for si in root.findall("a:si", ns):
            parts = [t.text or "" for t in si.findall(".//a:t", ns)]
            strings.append("".join(parts))
        return strings
    except (KeyError, Exception):
        return []

def _xlsx_cell_value(cell, shared_strings: List[str]) -> str:
    t = cell.get("t")
    v = cell.find("./v")
    is_node = cell.find("./is")
    if t == "s":
        if v is not None and v.text is not None:
            try:
                idx = int(v.text)
                return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
            except Exception:
                return ""
        return ""
    if t == "inlineStr" and is_node is not None:
        parts = [n.text or "" for n in is_node.findall(".//t")]
        return "".join(parts)
    if v is None or v.text is None:
        return ""
    return v.text

def read_xlsx_without_openpyxl(file_bytes: bytes, header_row: Optional[int] = DEFAULT_HEADER_ROW) -> pd.DataFrame:
    """
    Parse first worksheet of an .xlsx file using zipfile + ElementTree.
    Limitations: styles/dates/formulas not evaluated; merged cells not handled.
    """
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        sheets = _xlsx_list_worksheets(zf)
        if not sheets:
            raise ValueError("XLSX 내부에서 시트를 찾을 수 없습니다.")
        target = sheets[0]
        shared = _xlsx_load_shared_strings(zf)
        with zf.open(target) as fp:
            tree = ET.parse(fp)
        root = tree.getroot()
        ns_uri = root.tag.split("}")[0].strip("{")
        ns = {"a": ns_uri}
        rows = []
        for row in root.findall(".//a:sheetData/a:row", ns):
            values = []
            cells = row.findall("./a:c", ns)
            for c in cells:
                values.append(_xlsx_cell_value(c, shared))
            rows.append(values)

    maxlen = max((len(r) for r in rows), default=0)
    norm = [r + [""] * (maxlen - len(r)) for r in rows]

    if header_row is not None and 1 <= header_row <= len(norm):
        header = [h.strip() for h in norm[header_row - 1]]
        data = norm[header_row:]
        df = pd.DataFrame(data, columns=header)
    else:
        df = pd.DataFrame(norm)
    df = df.fillna("").astype(str)
    return df

# -----------------------------
# Paths
# -----------------------------
def default_storage_path() -> Path:
    try:
        base = Path(__file__).parent
    except NameError:
        base = Path.cwd()
    return base / "keywords_db.csv"

def hits_log_path() -> Path:
    try:
        base = Path(__file__).parent
    except NameError:
        base = Path.cwd()
    return base / "keywords_hits_log.csv"

def get_config_path() -> Path:
    """드롭다운 설정 파일 경로"""
    try:
        base = Path(__file__).parent
    except NameError:
        base = Path.cwd()
    return base / CONFIG_FILE_NAME

# -----------------------------
# Constants & defaults
# -----------------------------

DISPLAY_F_COL = "리스크 등급별 세부 심의기준 (셀을 더블 클릭하여 전체 내용을 확인하세요)"
RAW_F_COL = "리스크 등급별 세부 심의기준"

# ---- Dynamic DB column order helpers ----
def get_db_cols():
    try:
        cols = list(st.session_state.get("db_cols_order") or [])
        if cols:
            return cols
    except Exception:
        pass
    return DB_COLS


def _rename_fcol(df):
    """UI 표시용으로만 RAW_F_COL → DISPLAY_F_COL 헤더를 변경합니다."""
    try:
        import pandas as _pd
        # Styler가 들어오면 원본 DataFrame을 가져와 컬럼만 바꾸고 다시 스타일 적용
        if hasattr(df, 'to_excel') and hasattr(df, 'style'):
            # DataFrame (가급적 이 분기로)
            return df.rename(columns={RAW_F_COL: DISPLAY_F_COL})
        # pandas Styler 처리
        if getattr(df, '__class__', None).__name__ == 'Styler':
            base = getattr(df, 'data', None)
            if base is not None and hasattr(base, 'rename'):
                return base.rename(columns={RAW_F_COL: DISPLAY_F_COL}).style
        # 그 외 객체도 columns 속성이 있으면 시도
        if hasattr(df, 'rename') and hasattr(df, 'columns'):
            return df.rename(columns={RAW_F_COL: DISPLAY_F_COL})
        return df
    except Exception:
        return df
DEFAULT_CATEGORIES = ["공통(전체)", "식품", "건강기능식품", "화장품", "공산품"]
CATEGORY_PREFIX = {"공통(전체)":"A", "식품":"F","건강기능식품":"G","화장품":"B","공산품":"I"}

RISK_OPTIONS = ["1등급(사용금지)","2등급(대체키워드사용)","3등급(조건부사용)","4등급(사용가능)","5등급(테스트 등급)"]

DEFAULT_DETAIL_CRITERIA = ["-","실증자료제출","시험성적서제출","기능입증자료제출","표시기준준수","전문의견서","문헌자료제출"]
DEFAULT_EVIDENCE_TYPES = ["-","인체적용시험결과서","기능성평가보고서","임상시험결과보고서","실험데이터요약서","제품성분분석표","문헌자료","시험성적서"]
DEFAULT_ALT_KEYWORDS = ["-","탄력","보습","진정","미백","주름개선","자외선차단","영양공급"]

RISK_COLORS = {
    "1등급(사용금지)": "#ff6b6b",
    "2등급(대체키워드사용)": "#ffa94d",
    "3등급(조건부사용)": "#ffd43b",
    "4등급(사용가능)": "#a9e34b",
    "5등급(테스트 등급)": "#d8f5a2",
}

# Regex patterns (compiled once for performance)
_bracket_pairs = r"\(\)\[\]{}（）【】"
# kwd_no는 접두사(영문 대문자 1자 이상) + 숫자(3자리 이상) 패턴을 기본으로 가정
# 예: A001, US000, USA0123
_kwd_no_pattern = re.compile(r"^([A-Z]+)(\d{3,})$")
_kwd_split_pattern = re.compile(r"^([A-Za-z]+)(\d+)$")
_custom_kwd_pattern = re.compile(r"^([A-Za-z]+)(\d{1,})$")

# -----------------------------
# Dropdown config persistence (JSON)
# -----------------------------
def load_dropdown_config() -> dict:
    """JSON 파일에서 드롭다운 설정 불러오기"""
    if cloud_enabled():
        config = SupabaseRepository().load_setting('dropdown_config', None)
        if config is not None:
            return config
    config_path = get_config_path()
    if not cloud_enabled() and config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"드롭다운 설정을 불러오는 중 오류 발생: {e}")

    # 파일이 없거나 오류 시 기본값 반환
    return {
        "opt_categories": DEFAULT_CATEGORIES.copy(),
        "opt_risks": RISK_OPTIONS.copy(),
        "opt_details": DEFAULT_DETAIL_CRITERIA.copy(),
        "opt_evidences": DEFAULT_EVIDENCE_TYPES.copy(),
        "opt_alt_terms": DEFAULT_ALT_KEYWORDS.copy()
    }

def save_dropdown_config():
    """현재 드롭다운 설정을 JSON 파일로 저장"""
    _require_admin()
    normalize_dropdown_lists()
    config_path = get_config_path()
    config = {
        "opt_categories": st.session_state.opt_categories,
        "opt_risks": st.session_state.opt_risks,
        "opt_details": st.session_state.opt_details,
        "opt_evidences": st.session_state.opt_evidences,
        "opt_alt_terms": st.session_state.opt_alt_terms
    }
    try:
        if cloud_enabled():
            SupabaseRepository().save_setting('dropdown_config', config)
            return
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"드롭다운 설정 저장 중 오류: {e}")


# -----------------------------
# Dropdown normalize helpers (ko sort + '-' last)
# -----------------------------
def _ko_sorted(seq):
    try:
        import locale
        locale.setlocale(locale.LC_COLLATE, 'ko_KR.UTF-8')
        key = locale.strxfrm
        return sorted(seq, key=key)
    except Exception:
        return sorted(seq)


def unique_values_from_db(col: str) -> list:
    """Return ko-sorted unique, non-empty values for a given column from the current DB."""
    try:
        df = st.session_state.kw_df
        if df is None or df.empty or col not in df.columns:
            return []
        vals = df[col].astype(str).str.strip()
        uniq = [v for v in vals.unique().tolist() if v]
        return _ko_sorted(uniq)
    except Exception:
        return []
def _dedup_keep_order(seq):
    seen = set()
    out = []
    for x in seq:
        x = (x or "").strip()
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def normalize_dropdown_lists():
    """Ensure details/evidences/alt_terms are ko-sorted and '-' placed last & present."""
    # 대상 목록: opt_details, opt_evidences, opt_alt_terms
    targets = ["opt_details", "opt_evidences", "opt_alt_terms"]
    for key in targets:
        lst = list(getattr(st.session_state, key, []) or [])
        # clean & dedup
        lst = _dedup_keep_order(lst)
        # remove '-' temporarily
        without_dash = [x for x in lst if x != "-"]
        # ko sort
        without_dash = _ko_sorted(without_dash)
        # append '-' at the end (guarantee presence)
        without_dash.append("-")
        setattr(st.session_state, key, without_dash)


def _dropdown_with_input_option(lst):
    """Return normalized list for selectbox: ko-sorted with '-' last, plus '(직접 입력)' at the end."""
    tmp = _dedup_keep_order(lst)
    tmp = [x for x in tmp if x != "-"]
    tmp = _ko_sorted(tmp)
    tmp.append("-")
    return tmp + ["(직접 입력)"]

# -----------------------------
# Persistence helpers (with encoding fallbacks)
# -----------------------------
def read_csv_with_fallback_bytes(raw: bytes) -> pd.DataFrame:
    last_err = None
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin1"]:
        try:
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc).fillna("")
        except Exception as e:
            last_err = e
            continue
    raise last_err

def _ensure_counter_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "키워드 조회 수(누적카운트)" not in df.columns:
        df["키워드 조회 수(누적카운트)"] = "0"
    if "마지막 출력일자" not in df.columns:
        df["마지막 출력일자"] = ""
    if "키워드 등록일자" not in df.columns:
        df["키워드 등록일자"] = ""
    return df

def load_db(path: Path) -> pd.DataFrame:
    if cloud_enabled():
        df = SupabaseRepository().load_keywords()
        st.session_state.cloud_revision = df.attrs['revision']
        df = _ensure_counter_columns(df)
        st.session_state.db_cols_order = list(df.columns)
        return df
    if path.exists():
        try:
            raw = path.read_bytes()
            df = read_csv_with_fallback_bytes(raw)
            for c in DB_COLS:
                if c not in df.columns:
                    df[c] = "0" if c == "키워드 조회 수(누적카운트)" else ""
            df = _ensure_counter_columns(df)
            return df
        except Exception as e:
            st.warning(f"저장된 DB를 읽는 중 오류가 발생했습니다: {e}")
    df = pd.DataFrame(columns=DB_COLS)
    df = _ensure_counter_columns(df)
    return df

def save_db(df: pd.DataFrame, path: Path) -> None:
    _require_admin()
    if cloud_enabled():
        try:
            SupabaseRepository().save_keywords(df[get_db_cols()], st.session_state.get('cloud_revision'))
            st.session_state.kw_df = load_db(path)
        except (StorageError, ValueError, PermissionError) as e:
            st.session_state.kw_df = load_db(path)
            st.error(str(e))
            st.stop()
        return
    from pathlib import Path as _P


    try:
        _P(path).parent.mkdir(parents=True, exist_ok=True)
        sorted_df = sort_db_internal(df)
        sorted_df[get_db_cols()].to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"DB 저장 중 오류: {e}")
        st.stop()

def append_hits_log(kwd_list: List[str]) -> None:
    if not kwd_list:
        return
    log_p = hits_log_path()
    ts = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    rows = [{"ts": ts, "kwd_no": k} for k in kwd_list if k]
    df = pd.DataFrame(rows, columns=["ts","kwd_no"])
    try:
        if log_p.exists():
            df.to_csv(log_p, mode="a", header=False, index=False, encoding="utf-8-sig")
        else:
            df.to_csv(log_p, mode="w", header=True, index=False, encoding="utf-8-sig")
    except Exception as e:
        st.warning(f"로그 저장 실패: {e}")
    # 조회 로그가 변경되면 캐시 무효화
    try:
        _cache_data.clear()
    except Exception:
        pass

@_cache_data(show_spinner=False, ttl=30)
def load_hits_log() -> pd.DataFrame:
    if cloud_enabled():
        return SupabaseRepository().load_hits()
    log_p = hits_log_path()
    if not log_p.exists():
        return pd.DataFrame(columns=["ts","kwd_no"])
    try:
        return pd.read_csv(log_p, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return pd.DataFrame(columns=["ts","kwd_no"])

def overwrite_hits_log(df: pd.DataFrame) -> None:
    """Overwrite the hits log CSV safely with utf-8-sig encoding."""
    _require_admin()
    if cloud_enabled():
        raise StorageError('클라우드 로그는 전체 덮어쓰기를 지원하지 않습니다.')
    log_p = hits_log_path()
    try:
        df.to_csv(log_p, mode="w", header=True, index=False, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"조회 로그 저장 중 오류: {e}")
    # 전체 로그를 덮어썼으므로 캐시 무효화
    try:
        _cache_data.clear()
    except Exception:
        pass

# -----------------------------
# Sorting helpers
# -----------------------------

def _split_kwd_series(s):
    s = s.astype(str)
    m = s.str.extract(_kwd_split_pattern)
    pref = m[0].fillna("")
    num = m[1].fillna("0").astype(int)
    return pref, num

def sort_db_internal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "kwd_no" not in df.columns:
        return df
    pref, num = _split_kwd_series(df["kwd_no"])
    sorted_df = (
        df.assign(_pref=pref, _num=num)
        .sort_values(by=["상품카테고리", "_pref", "_num", "키워드명"], kind="mergesort")
        .drop(columns=["_pref", "_num"])
        .reset_index(drop=True)
    )
    return sorted_df

def sort_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "kwd_no" not in df.columns:
        return df
    pref, num = _split_kwd_series(df["kwd_no"])
    sorted_df = (
        df.assign(_pref=pref, _num=num)
        .sort_values(by=["_pref", "_num", "키워드명"], kind="mergesort")
        .drop(columns=["_pref", "_num"])
        .reset_index(drop=True)
    )
    return sorted_df


# -----------------------------
# Session init & numbering helpers
# -----------------------------
def init_state():
    legacy_relaxed = bool(st.session_state.get('exact_relaxed', True))
    for name in ('strip_bracket_notes', 'normalize_whitespace', 'normalize_symbols'):
        st.session_state.setdefault(name, legacy_relaxed)
    st.session_state.setdefault('ignore_case', True)
    if "storage_path" not in st.session_state:
        st.session_state.storage_path = str(default_storage_path())
    if "kw_df" not in st.session_state:
        st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
        # Record DB column order as loaded
        try:
            st.session_state.db_cols_order = list(st.session_state.kw_df.columns)
        except Exception:
            st.session_state.db_cols_order = list(DB_COLS)

    # 드롭다운 설정을 JSON 파일에서 불러오기
    if "opt_categories" not in st.session_state:
        config = load_dropdown_config()
        st.session_state.opt_categories = config["opt_categories"]
        st.session_state.opt_risks = config["opt_risks"]
        st.session_state.opt_details = config["opt_details"]
        st.session_state.opt_evidences = config["opt_evidences"]
        st.session_state.opt_alt_terms = config["opt_alt_terms"]
        normalize_dropdown_lists()

    # 유사일치 조사/어미(접미사) 화이트리스트(사용자 추가분) 로드
    if "ko_suffix_whitelist_extra" not in st.session_state:
        st.session_state.ko_suffix_whitelist_extra = load_suffix_whitelist_config()
    if "suffix_suggestions" not in st.session_state:
        st.session_state.suffix_suggestions = {}

# 정규화(괄호 제거/공백 정규화/영문 대소문자 무시) 옵션과 함께 사용할
# 특수기호 무시(공백 치환) 리스트 로드

    # 특수기호 무시(공백 치환) 설정 로드
    if "ignored_special_symbols" not in st.session_state:
        st.session_state.ignored_special_symbols = load_ignored_special_symbols_config()

    # 키워드 번호 카운터 초기화
    if "counters" not in st.session_state:
        st.session_state.counters = {}

def scan_existing_counters():
    for v in st.session_state.kw_df["kwd_no"].dropna().astype(str):
        m = _kwd_no_pattern.match(v.strip())
        if not m:
            continue
        pfx, num = m.group(1), int(m.group(2))
        st.session_state.counters[pfx] = max(st.session_state.counters.get(pfx, 0), num)

def get_prefix(category: str) -> str:
    if category in CATEGORY_PREFIX:
        return CATEGORY_PREFIX[category]
    first = (category[:1] or "U").upper()
    return first if re.match(r"[A-Z]", first) else "U"

def infer_prefix_from_existing(category: str) -> str:
    df = st.session_state.kw_df
    if df is not None and not df.empty:
        sub = df[df["상품카테고리"].astype(str).str.strip() == str(category).strip()]["kwd_no"].dropna().astype(str)
        if not sub.empty:
            # 기존 데이터에서 prefix(대문자 1자 이상) 분포를 기반으로 가장 흔한 prefix를 선택
            pref = sub.str.extract(r"^([A-Z]+)(\d{3,})$")[0].dropna()
            if not pref.empty:
                return pref.value_counts().idxmax()
    return get_prefix(category)

def _infer_number_width_from_existing(category: str, pfx: str) -> int:
    """해당 카테고리/접두사에서 사용 중인 숫자 자리수를 추정합니다.
    - 예: US000 → 3, ABC0001 → 4
    - 없으면 기본 3
    """
    try:
        df = st.session_state.kw_df
        if df is None or df.empty:
            return 3
        sub = df[df["상품카테고리"].astype(str).str.strip() == str(category).strip()]["kwd_no"].dropna().astype(str)
        if sub.empty:
            return 3
        nums = sub.str.extract(r"^%s(\d+)$" % re.escape(str(pfx)))[0].dropna().astype(str)
        if nums.empty:
            return 3
        return max(3, int(nums.str.len().max()))
    except Exception:
        return 3

def next_kwd_no(category: str) -> str:
    pfx = infer_prefix_from_existing(category)
    df = st.session_state.kw_df
    next_num = None
    width = _infer_number_width_from_existing(category, pfx)
    if df is not None and not df.empty:
        sub = df[df["상품카테고리"].astype(str).str.strip() == str(category).strip()]["kwd_no"].astype(str)
        nums = sub.str.extract(r"^%s(\d+)$" % re.escape(str(pfx)))[0].dropna()
        if not nums.empty:
            next_num = int(nums.astype(int).max()) + 1
    if next_num is None:
        cur = st.session_state.counters.get(pfx, 0) + 1
        st.session_state.counters[pfx] = cur
        next_num = cur
    else:
        st.session_state.counters[pfx] = max(st.session_state.counters.get(pfx, 0), next_num)
    return f"{pfx}{next_num:0{width}d}"

def preview_next_kwd_no(category: str) -> str:
    """next_kwd_no와 동일한 규칙으로 '다음 번호'를 미리 계산합니다.
    - st.session_state.counters를 변경하지 않습니다(미리보기 전용).
    """
    pfx = infer_prefix_from_existing(category)
    df = st.session_state.kw_df
    next_num = None
    width = _infer_number_width_from_existing(category, pfx)

    if df is not None and not df.empty:
        sub = df[df["상품카테고리"].astype(str).str.strip() == str(category).strip()]["kwd_no"].astype(str)
        nums = sub.str.extract(r"^%s(\d+)$" % re.escape(str(pfx)))[0].dropna()
        if not nums.empty:
            next_num = int(nums.astype(int).max()) + 1

    if next_num is None:
        # 실제 next_kwd_no는 counter를 증가시키지만, 여기서는 값을 '예측'만 합니다.
        cur = st.session_state.counters.get(pfx, 0) + 1
        next_num = cur

    return f"{pfx}{next_num:0{width}d}"

def category_kwdno_diagnostics(category: str, dropdown_options: list[str] | None = None) -> dict:
    """카테고리명 일치 여부와 DB 내 kwd_no 현황을 점검하기 위한 진단 정보를 반환합니다."""
    category_raw = "" if category is None else str(category)
    category_stripped = category_raw.strip()

    dropdown_options = dropdown_options or []
    exact_in_dropdown = category_raw in dropdown_options
    stripped_in_dropdown = category_stripped in [str(o).strip() for o in dropdown_options]

    # 비슷한 후보(공백 제거 후 비교, 대/소문자 무시)
    def _norm(s: str) -> str:
        return re.sub(r"\s+", "", str(s)).lower()

    norm_target = _norm(category_raw)
    near = []
    if norm_target:
        for o in dropdown_options:
            if _norm(o) == norm_target and o not in near:
                near.append(o)

    df = st.session_state.kw_df
    cat_df = None
    kwd_list = []
    prefix_counts = {}
    inferred_prefix = infer_prefix_from_existing(category_raw)
    prefix_source = "existing"  # default

    if category_raw in CATEGORY_PREFIX:
        prefix_source = "mapping"
    else:
        # 기존 데이터가 없으면 get_prefix로 떨어짐
        _tmp = df[df["상품카테고리"].astype(str).str.strip() == category_stripped] if (df is not None and not df.empty) else None
        if _tmp is None or _tmp.empty:
            prefix_source = "fallback"

    if df is not None and not df.empty and category_stripped:
        cat_df = df[df["상품카테고리"].astype(str).str.strip() == category_stripped].copy()
        if cat_df is not None and not cat_df.empty:
            kwd_list = cat_df["kwd_no"].dropna().astype(str).str.upper().tolist()
            # prefix 분포 (정규식에 맞는 것만)
            for k in kwd_list:
                mm = re.match(r"^([A-Z]+)(\d{3,})$", k)
                if mm:
                    prefix_counts[mm.group(1)] = prefix_counts.get(mm.group(1), 0) + 1

    return {
        "category_raw": category_raw,
        "category_stripped": category_stripped,
        "exact_in_dropdown": exact_in_dropdown,
        "stripped_in_dropdown": stripped_in_dropdown,
        "near_matches": near,
        "db_rows_in_category": 0 if cat_df is None else int(len(cat_df)),
        "kwd_no_samples": kwd_list[:20],
        "prefix_counts": prefix_counts,
        "inferred_prefix": inferred_prefix,
        "prefix_source": prefix_source,
        "preview_next_kwd_no": preview_next_kwd_no(category_raw) if category_stripped else None,
    }


def normalize_upload(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]
    mapping = {
        "kwd_no": "kwd_no",
        "keyword_no": "kwd_no",
        "키워드no": "kwd_no",
        "키워드 no": "kwd_no",
        "키워드명": "키워드명",
        "term": "키워드명",
        "상품카테고리": "상품카테고리",
        "category": "상품카테고리",
        "리스크 등급": "리스크 등급",
        "risk": "리스크 등급",
        "리스크 등급별 세부 심의기준": "리스크 등급별 세부 심의기준",
        "세부 심의기준": "리스크 등급별 세부 심의기준",
        "증빙자료유형": "증빙자료유형",
        "증빙자료": "증빙자료유형",
        "대체키워드": "대체키워드",
        "대체키워드명": "대체키워드"
    }
    rename_dict = {col: mapping[col] for col in d.columns if col in mapping}
    if rename_dict:
        d = d.rename(columns=rename_dict)
    for col in DB_COLS:
        if col not in d.columns:
            if col == "키워드 조회 수(누적카운트)":
                d[col] = "0"
            elif col == "마지막 출력일자":
                d[col] = ""
            else:
                d[col] = "" if col != "kwd_no" else None
    d = d[get_db_cols()]
    for c in d.columns:
        d[c] = d[c].astype(str).str.strip()
    return d


# --- Korean postposition/ending whitelist for fuzzy matching ---
# Used to treat patterns like '여드름에는' as a fuzzy hit for keyword '여드름' (highlighting only the stem).

# ---- Suffix whitelist persistence & UI helpers ----
_SUFFIX_CONFIG_PATH = Path(__file__).with_name("ko_suffix_whitelist.json")

def load_suffix_whitelist_config() -> list:
    """Load user-managed Korean suffix whitelist additions from JSON.
    Returns a list of suffix strings (may be empty).
    """
    if cloud_enabled():
        return SupabaseRepository().load_setting('ko_suffix_whitelist', {'extra_suffixes': []})['extra_suffixes']
    try:
        if _SUFFIX_CONFIG_PATH.exists():
            data = json.loads(_SUFFIX_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                items = data.get("extra_suffixes", [])
            else:
                items = data
            if isinstance(items, list):
                return [str(x).strip() for x in items if str(x).strip()]
    except Exception:
        pass
    return []

def save_suffix_whitelist_config(extra_suffixes: list) -> bool:
    """Persist user-managed suffix whitelist additions to JSON."""
    _require_admin()
    try:
        payload = {"extra_suffixes": [str(x).strip() for x in (extra_suffixes or []) if str(x).strip()]}
        if cloud_enabled():
            SupabaseRepository().save_setting('ko_suffix_whitelist', payload)
            return True
        _SUFFIX_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def get_ko_suffix_whitelist() -> set:
    """Return merged whitelist = default + user additions from session_state."""
    wl = set(_KO_SUFFIX_WHITELIST)
    try:
        extra = st.session_state.get("ko_suffix_whitelist_extra", []) or []
        for x in extra:
            x = str(x).strip()
            if x:
                wl.add(x)
    except Exception:
        pass
    return wl


# --- Ignored special symbols whitelist (for relaxed normalization) ---
# When '(괄호 제거·공백 정규화·영문 대소문자 무시)' is enabled, we can additionally
# treat configured special symbols as whitespace (replace with space, length preserved).
_SPECIAL_SYMBOLS_CONFIG_PATH = Path(__file__).with_name("ignored_special_symbols.json")

def load_ignored_special_symbols_config() -> list:
    """Load user-managed ignored special symbols list from JSON.
    Returns a list of *single-character* symbols.
    """
    if cloud_enabled():
        value = SupabaseRepository().load_setting('ignored_special_symbols', None)
        return value['symbols'] if value is not None else _DEFAULT_IGNORED_SPECIAL_SYMBOLS.copy()
    try:
        if _SPECIAL_SYMBOLS_CONFIG_PATH.exists():
            data = json.loads(_SPECIAL_SYMBOLS_CONFIG_PATH.read_text(encoding="utf-8"))
            items = None
            if isinstance(data, dict):
                items = data.get("symbols", [])
            elif isinstance(data, list):
                items = data
            if isinstance(items, list):
                out = []
                for x in items:
                    x = str(x)
                    if len(x) == 1 and x.strip() != "":
                        out.append(x)
                # dedup keep order
                seen = set()
                cleaned = []
                for ch in out:
                    if ch not in seen:
                        seen.add(ch)
                        cleaned.append(ch)
                return cleaned
    except Exception:
        pass
    return _DEFAULT_IGNORED_SPECIAL_SYMBOLS.copy()

def save_ignored_special_symbols_config(symbols: list) -> bool:
    """Persist ignored special symbols list to JSON."""
    _require_admin()
    try:
        cleaned = []
        seen = set()
        for x in (symbols or []):
            x = str(x)
            if len(x) != 1:
                continue
            if x.strip() == "":
                continue
            if x not in seen:
                seen.add(x)
                cleaned.append(x)
        payload = {"symbols": cleaned}
        if cloud_enabled():
            SupabaseRepository().save_setting('ignored_special_symbols', payload)
            return True
        _SPECIAL_SYMBOLS_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def get_ignored_special_symbols() -> list:
    """Return current ignored special symbols list (single-character)."""
    try:
        syms = st.session_state.get("ignored_special_symbols", None)
        if isinstance(syms, list) and syms:
            return [str(x) for x in syms if isinstance(x, str) and len(x) == 1 and x.strip() != ""]
    except Exception:
        pass
    return _DEFAULT_IGNORED_SPECIAL_SYMBOLS.copy()


def _matching_config() -> MatchingConfig:
    """Copy current UI settings into the independent engine's explicit input."""
    selected_mode = {label: mode for mode, label in MATCH_MODES.items()}.get(
        st.session_state.get('match_mode'), 'exact')
    return MatchingConfig(
        ignored_symbols=tuple(get_ignored_special_symbols()),
        ko_suffixes=frozenset(get_ko_suffix_whitelist()),
        mode='exact' if selected_mode == 'exact' else 'partial',
        exact_relaxed=bool(st.session_state.get('exact_relaxed', True)),
        strip_bracket_notes=bool(st.session_state.get('strip_bracket_notes', True)),
        normalize_whitespace=bool(st.session_state.get('normalize_whitespace', True)),
        ignore_case=bool(st.session_state.get('ignore_case', True)),
        normalize_symbols=bool(st.session_state.get('normalize_symbols', True)),
        partial_min_len=2 if selected_mode == 'similar' else int(st.session_state.get('partial_min_len', 2) or 2),
        similar_reverse_single=False,
        similar_reverse_any=False,
    )


def find_matches(text, kw_df, match_mode="유사 키워드 포함", exact_relaxed=False,
                 suffix_suggestions=None, **kwargs) -> List[Match2]:
    return _engine_find_matches(
        text, kw_df, match_mode=match_mode, exact_relaxed=exact_relaxed,
        suffix_suggestions=suffix_suggestions, config=_matching_config(), **kwargs,
    )


def find_matches_nlp(text, kw_df, match_mode="유사 키워드 포함", exact_relaxed=False,
                     suffix_suggestions=None, **kwargs) -> List[Match2]:
    return _engine_find_matches_nlp(
        text, kw_df, match_mode=match_mode, exact_relaxed=exact_relaxed,
        suffix_suggestions=suffix_suggestions, config=_matching_config(), **kwargs,
    )


def build_kwd_tooltip_attr(kwd_no: str) -> str:
    """kwd_no에 해당하는 키워드 리스트(kw_df)의 행(ROW) 전체 정보를 tooltip용 문자열로 변환합니다.
    HTML attribute로 넣기 위해 quote-safe escaping + 줄바꿈 엔티티(&#10;) 처리까지 수행합니다.
    """
    try:
        df = st.session_state.get("kw_df", None)
    except Exception:
        df = None

    if df is None or getattr(df, "empty", True):
        tip = f"kwd_no: {kwd_no}\n(키워드 리스트가 로드되지 않았습니다)"
        return html.escape(tip, quote=True).replace("\n", "&#10;")

    if "kwd_no" not in df.columns:
        tip = f"kwd_no: {kwd_no}\n(kw_df에 'kwd_no' 컬럼이 없습니다)"
        return html.escape(tip, quote=True).replace("\n", "&#10;")

    try:
        sub = df[df["kwd_no"].astype(str).str.strip() == str(kwd_no).strip()]
        if sub.empty:
            tip = f"kwd_no: {kwd_no}\n(해당 번호의 행을 찾지 못했습니다)"
            return html.escape(tip, quote=True).replace("\n", "&#10;")

        row = sub.iloc[-1]
        parts = []
        for col, val in row.items():
            # NaN/None 제외
            try:
                if pd.isna(val):
                    continue
            except Exception:
                pass
            sval = str(val).strip()
            if not sval:
                continue
            parts.append(f"{col}: {sval}")

        tip = "\n".join(parts) if parts else f"kwd_no: {kwd_no}"
        return html.escape(tip, quote=True).replace("\n", "&#10;")
    except Exception as e:
        tip = f"kwd_no: {kwd_no}\n(tooltip 생성 중 오류: {e})"
        return html.escape(tip, quote=True).replace("\n", "&#10;")


def build_kwd_tooltip_html(kwd_no: str) -> str:
    """kwd_no에 해당하는 키워드 리스트(kw_df)의 행(ROW)을 HTML tooltip로 생성합니다.

    중요:
    - 툴팁은 하이라이트 미리보기 영역 내부에서 `.kwdno-wrap:hover .kwd-tooltip` CSS로 표시됩니다.
    - 기존 구현은 `<span class='kwdno-wrap'>` 내부에 `<div>/<table>`을 삽입하여 (HTML 중첩 규칙 위반)
      브라우저가 DOM을 재배치하는 경우가 발생했고, 그때 hover 셀렉터가 깨져
      "일부만 툴팁이 뜨지 않는" 문제가 나타날 수 있었습니다.
    - 이를 방지하기 위해 툴팁 마크업을 *phrasing content*만으로 구성합니다.
      (span + br 기반의 라인 리스트; div/table 미사용)
    """
    try:
        df = st.session_state.get("kw_df", None)
    except Exception:
        df = None

    def _msg_box(msg: str) -> str:
        # span 기반(phrasing-only) tooltip
        return (
            "<span class='kwd-tooltip'>"
            f"<span class='kwd-tooltip-line' style='font-size:12px; white-space:pre-line;'>{html.escape(msg)}</span>"
            "</span>"
        )

    if df is None or getattr(df, "empty", True):
        return _msg_box(f"kwd_no: {kwd_no}\\n(키워드 리스트가 로드되지 않았습니다)")

    if "kwd_no" not in df.columns:
        return _msg_box(f"kwd_no: {kwd_no}\\n(kw_df에 'kwd_no' 컬럼이 없습니다)")

    try:
        sub = df[df["kwd_no"].astype(str).str.strip() == str(kwd_no).strip()]
        if sub.empty:
            return _msg_box(f"kwd_no: {kwd_no}\\n(해당 번호의 행을 찾지 못했습니다)")

        row = sub.iloc[-1]
        cols = list(df.columns)


        # 기본 툴팁에서 제외할 컬럼(요청사항)
        _exclude_cols = {
            '키워드 조회 수(누적카운트)',
            '마지막 출력일자',
            '키워드등록일자',
            '키워드등록인',
        }
        cols = [c for c in cols if str(c).strip() not in _exclude_cols]
        lines = []
        for c in cols:
            v = row.get(c, "")
            try:
                if pd.isna(v):
                    v = ""
            except Exception:
                pass
            # 각 라인은 span + <br> 형태로 구성(유효한 in-span 구조)
            lines.append(
                f"<span class='kwd-tt-row'>"
                f"<span class='kwd-tt-k'>{html.escape(str(c))}</span>"
                f"<span class='kwd-tt-v'>{html.escape(str(v))}</span>"
                f"</span>"
            )

        # 표처럼 보이도록 row들을 연속 배치 (phrasing-only)
        body = "".join(lines)
        return f"<span class='kwd-tooltip'>{body}</span>"
    except Exception as e:
        return _msg_box(f"kwd_no: {kwd_no}\\n(tooltip 생성 중 오류: {e})")


def build_kwd_tooltip_data(kwd_no: str):
    """Return tooltip rows as list of (col, val) pairs for kwd_no.
    This data is used ONLY for hover tooltip rendering (not inserted into preview body)."""
    try:
        df = st.session_state.get('kw_df')
        if df is None or len(df) == 0:
            return [("kwd_no", kwd_no), ("msg", "DB가 로드되지 않았습니다.")]
        sub = df[df["kwd_no"].astype(str).str.strip() == str(kwd_no).strip()]
        if sub is None or len(sub) == 0:
            return [("kwd_no", kwd_no), ("msg", "해당 번호의 행을 찾지 못했습니다.")]
        row = sub.iloc[-1]
        out = []
        for col, val in row.items():
            try:
                if pd.isna(val):
                    continue
            except Exception:
                pass
            sval = str(val).strip()
            if not sval:
                continue
            out.append((str(col), sval))
        if not out:
            out = [("kwd_no", kwd_no)]
        return out
    except Exception as e:
        return [("kwd_no", kwd_no), ("msg", f"tooltip 데이터 생성 오류: {e}")]


def highlight_text(text: str, matches: List[Match2]) -> str:
    """텍스트에 등급별 하이라이트를 적용하여 HTML 문자열로 반환합니다.

    핵심 개선:
    1) KWD_NO 표기는 기존처럼 괄호 포함 '(US036)' 형태를 유지하되,
       tooltip 매핑/조회는 항상 'US036' 같은 순수 토큰만 사용합니다.
       (괄호/공백/줄바꿈이 섞여도 정규화)
    2) 원문에 이미 '(US036 ...)' 같은 표기가 붙어있는 경우, 우리가 ids_html을 추가한 뒤
       원문에 남아있는 괄호 표기가 다시 렌더링되며 ')'만 다음 줄에 남는 문제가 생길 수 있어,
       하이라이트 구간 바로 뒤에 붙은 괄호표기(키워드번호 포함)를 "소비(건너뛰기)"합니다.
       → 원문엔 줄바꿈이 없어도 UI에서 ')'가 단독으로 내려가는 현상을 방지.
    """
    global HIGHLIGHT_TOOLTIP_MAP
    HIGHLIGHT_TOOLTIP_MAP = {}

    if not matches:
        return html.escape(text)

    def _risk_grade(r: str) -> int:
        r = (r or '').strip()
        if r.startswith('1'): return 1
        if r.startswith('2'): return 2
        if r.startswith('3'): return 3
        if r.startswith('4'): return 4
        if r.startswith('5'): return 5
        return 0

    text_colors = {1: '#e03131', 2: '#1c7ed6', 3: '#7048e8', 4: '#2f9e44'}

    _token_re = re.compile(r'([A-Za-z]{2})\s*([0-9]{3,})')

    def _extract_kwd_token(raw: str) -> str:
        s = "" if raw is None else str(raw)
        m = _token_re.search(s)
        if not m:
            return s.strip()
        return (m.group(1) + m.group(2)).upper()

    def _split_around_token(raw: str):
        s = "" if raw is None else str(raw)
        m = _token_re.search(s)
        if not m:
            return ("", s, "")
        head = s[:m.start()]
        token = (m.group(1) + m.group(2)).upper()
        tail = s[m.end():]
        return (head, token, tail)

    # (start, end) 구간별로 kwd_no / risk 정보 묶기
    spans = {}
    for m in matches:
        seg = text[m.start:m.end]
        if not seg:
            continue
        key = (m.start, m.end)
        info = spans.get(key)
        if info is None:
            info = {'seg': seg, 'ids_raw': [], 'risk_map': {}}
            spans[key] = info

        if m.kwd_no:
            info['ids_raw'].append(m.kwd_no)
            norm = _extract_kwd_token(m.kwd_no)
            info['risk_map'][norm] = _risk_grade(m.risk)

    if not spans:
        return html.escape(text)

    # Detection keeps every keyword. Only the visual highlight merges overlapping ranges.
    ordered = []
    for (start, end), info in sorted(spans.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        if ordered and start < ordered[-1][0][1]:
            (previous_start, previous_end), previous = ordered[-1]
            merged_end = max(previous_end, end)
            previous['seg'] = text[previous_start:merged_end]
            previous['ids_raw'].extend(info['ids_raw'])
            previous['risk_map'].update(info['risk_map'])
            ordered[-1] = ((previous_start, merged_end), previous)
        else:
            ordered.append(((start, end), info))

    result_parts = []
    cur = 0

    # 괄호 표기 소비용: 하이라이트 구간 직후의 "(...)"를 제거(건너뛰기)
    # - DOTALL로 줄바꿈 포함 가능
    # - 길이 제한을 두어 과도한 잡아먹기 방지
    paren_pat = re.compile(r'^[ \t\r\f\v\n]*\((.{0,200}?)\)', re.DOTALL)

    for (start, end), info in ordered:
        if start < cur:
            continue

        # 일반 텍스트 추가 (하이라이트 앞)
        if cur < start:
            result_parts.append(html.escape(text[cur:start]))

        seg = info['seg']
        ids_raw = info['ids_raw'] or []
        risk_map = info['risk_map'] or {}

        # Deduplicate kwd_no tokens for display (keep first occurrence; preserve order)
        # This prevents '(US206, US206, US206)' style repeats in highlight preview.
        _dedup = []
        _seen = set()
        for _raw in ids_raw:
            _norm = _extract_kwd_token(_raw) or str(_raw).strip()
            if _norm in _seen:
                continue
            _seen.add(_norm)
            _dedup.append(_raw)
        ids_raw = _dedup

        # kwd_no 링크 HTML 구성
        frag_parts = []
        for i, raw in enumerate(ids_raw):
            head, token, tail = _split_around_token(raw)
            norm = _extract_kwd_token(raw) or (token or str(raw).strip())

            g = risk_map.get(norm, 0)
            color = text_colors.get(g, 'inherit')
            # (개선안 A - 개선) 하이라이트 미리보기 영역에는 여전히 '사용자 입력 원문'만 표시하되,
            # 마우스오버 시 표 형태 커스텀 툴팁(kwd-tooltip)은 유지합니다.
            # 툴팁은 display:none 상태로 DOM에 포함되며 hover 시에만 노출되므로
            # 원문에 없는 텍스트가 본문에 섞여 보이지 않습니다.
            # Collect tooltip data separately; do NOT insert tooltip text into preview HTML
            HIGHLIGHT_TOOLTIP_MAP[norm] = build_kwd_tooltip_data(norm)

            # 표기 유지: 괄호/구분자도 같은 wrap 안에 포함시켜 hover 영역이 끊기지 않게 합니다.
            # - 첫 번째 항목: '('를 head 쪽에 포함(이미 head에 '('가 있으면 중복 방지)
            # - 마지막 항목: tail에 ')'가 있으면 그대로 두고, 없으면 suffix로 ')' 추가
            prefix = ""
            if i == 0 and "(" not in head:
                prefix = "("
            sep = ", " if i > 0 else ""
            suffix = ""
            if i == len(ids_raw) - 1:
                if ")" not in tail:
                    suffix = ")"

            frag_content = (
                f"{html.escape(sep + prefix)}"
                f"{html.escape(head)}"
                f"<span class='kwdno-link' data-kwd='{html.escape(norm)}' "
                f"style='color:{color}; text-decoration:underline; cursor:pointer'>"
                f"<b>{html.escape(token or norm)}</b></span>"
                f"{html.escape(tail + suffix)}"
            )
            frag_parts.append(f"<span class='kwdno-wrap'>{frag_content}</span>")

        ids_html = "".join(frag_parts)

        grades = {g for g in risk_map.values() if g}
        if len(grades) == 1:
            g = next(iter(grades))
            if g in (1, 2, 3, 4, 5):
                cls = f"hl-mark hl-risk{g}"
            else:
                cls = "hl-mark hl-riskN"
        else:
            cls = "hl-mark hl-riskN"

        leading_ws = seg[:len(seg) - len(seg.lstrip())]
        trailing_ws = seg[len(seg.rstrip()):]
        core = seg.strip()

        inner_html = f"【<b>{html.escape(core)}</b>】{ids_html}"
        decorated = f"{html.escape(leading_ws)}<span class='{cls}'>{inner_html}</span>{html.escape(trailing_ws)}"
        result_parts.append(decorated)

        # 원문 커서 이동: 기본은 end까지
        cur = end

        # 하이라이트 직후에 원문에 남아있는 "(US036 ...)" 같은 표기가 붙어있으면 소비(스킵)
        # → ')'가 다음 줄로 떨어져 보이는 현상 방지
        tail_text = text[cur:]
        mparen = paren_pat.match(tail_text)
        if mparen:
            inside = mparen.group(1) or ""
            if _token_re.search(inside):
                cur += mparen.end()

    # 남은 텍스트
    if cur < len(text):
        result_parts.append(html.escape(text[cur:]))

    return "".join(result_parts)
# -----------------------------
# Upload merge helpers (needed for v97)
# -----------------------------
def assign_missing_ids(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for i, row in out.iterrows():
        if not str(row.get("kwd_no", "")).strip():
            cat = str(row.get("상품카테고리", "")).strip() or "공통(전체)"
            out.at[i, "kwd_no"] = next_kwd_no(cat)
    return out

def merge_or_overwrite(base: pd.DataFrame, incoming: pd.DataFrame, mode: str) -> Tuple[pd.DataFrame, int, int]:
    inc = incoming.copy()
    before = len(inc)
    if "kwd_no" in inc.columns and inc["kwd_no"].astype(str).str.strip().any():
        inc = inc.sort_values(by=["kwd_no"]).drop_duplicates(subset=["kwd_no"], keep="last")
    else:
        inc = inc.sort_values(by=["키워드명", "상품카테고리"]).drop_duplicates(subset=["키워드명", "상품카테고리"], keep="last")
    dedup_removed = before - len(inc)

    if mode == "overwrite":
        return inc.reset_index(drop=True), len(inc), dedup_removed

    if base.empty:
        return inc.reset_index(drop=True), len(inc), dedup_removed

    if inc["kwd_no"].astype(str).str.strip().any():
        new_ids: Set[str] = set(inc["kwd_no"].astype(str))
        base = base[~base["kwd_no"].astype(str).isin(new_ids)]

    merged = pd.concat([base, inc], ignore_index=True)
    return merged, len(inc), dedup_removed

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Keyword Risk Analyzer", layout="wide")

# --- Compact button & row spacing ---
st.markdown("""
<style>
/* Reduce vertical gaps between rows of columns (affects button grids) */
div[data-testid="stHorizontalBlock"] {
    margin-bottom: 0rem;
}
/* Make buttons more compact (less vertical padding) */
div.stButton > button {
    padding-top: 0rem;
    padding-bottom: 0rem;
    min-height: 1.2rem;
}
</style>
""", unsafe_allow_html=True)
st.title("🔎 광고심의 자동화 솔루션(가칭)")

# --- Scroll margin for keyword anchor links ---
st.markdown("""
<style>
[id^="G"], [id^="F"], [id^="P"], [id^="K"] {
  scroll-margin-top: 100px;
}
</style>
""", unsafe_allow_html=True)

# --- Minimal wrap CSS (safe) ---
st.markdown(
    """
    <style>
    [data-testid="stDataFrame"] [role="gridcell"] {
        white-space: normal !important;
        word-break: break-word !important;
    }
    </style>
    """, unsafe_allow_html=True
)

st.markdown(
    """
<style>
.hl-box{{
  border:1px solid rgba(49,51,63,0.2);
  border-radius:8px;
  padding:12px;
  overflow: visible;
  background:#fff;
  white-space:pre-wrap;
  line-height:1.5;
  box-sizing:border-box;
}}
.hl-box .hl-scroll{{
  max-height:{MAX_HIGHLIGHT_HEIGHT}px;
  min-height:21.0em; /* ~3 lines (line-height 1.5) */
  overflow-y:auto;
  overflow-x:auto;
}}
/* 기존 mark 기반 하이라이트는 유지하되, span.hl-mark 클래스를 새로 정의 */
# .hl-box mark{{padding:0;border-radius:2px}}
.hl-box .hl-mark{{
  padding:0;
  border-radius:2px;
  color:#000;
}}
.hl-box .hl-risk5{{
  background:#d8f5a2 !important;
  background-color:#d8f5a2 !important;
}}
.hl-box .hl-riskN{{
  background:#ffd43b !important;
  background-color:#ffd43b !important;
}}
[data-testid="stDataFrame"] div{{white-space:normal !important;}}
/* kwd_no hover tooltip (table-style) */
.hl-box .kwdno-wrap{{
  position: relative;
  display: inline-block;
}}
.hl-box .kwd-tooltip{{
  display: none;
  position: absolute;
  left: 0;
  top: 1.6em;
  z-index: 9999;
  max-width: 92vw;
            min-width: 420px;
            width: min(720px, 92vw);
  max-height: 280px;
  overflow: auto;
  background: #f3f3f3;
  color: #111;
  border: 1px solid rgba(0,0,0,0.15);
  border-radius: 10px;
  box-shadow: 0 10px 28px rgba(0,0,0,0.18);
  padding: 8px 10px;
}}
.hl-box .kwd-tooltip-line{{
  display: block;
  font-size: 12px;
  line-height: 1.35;
  white-space: normal;
}}

.hl-box .kwd-tooltip{{
  /* 표처럼 보이도록 기본 폭/레이아웃을 조금 더 안정적으로 */
  min-width: 320px;
  row-gap: 2px;
}}
.hl-box .kwd-tt-row{{
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: 10px;
  align-items: start;
  padding: 2px 0;
}}
.hl-box .kwd-tt-k{{
  font-weight: 700;
  white-space: nowrap;
}}
.hl-box .kwd-tt-v{{
  /* DB에 저장된 줄바꿈/문단 구분을 그대로 표시 */
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
.hl-box .kwdno-wrap:hover .kwd-tooltip{{
  display: inline-grid;
}}
.hl-box table.kwd-tooltip-table{{
  border-collapse: collapse;
  font-size: 12px;
  line-height: 1.35;
}}
.hl-box table.kwd-tooltip-table th{{
  position: sticky;
  top: 0;
  background: #f6f7f9;
  font-weight: 600;
  white-space: nowrap;
}}
.hl-box table.kwd-tooltip-table th,
.hl-box table.kwd-tooltip-table td{{
  border: 1px solid rgba(0,0,0,0.08);
  padding: 4px 6px;
  vertical-align: top;
}}
.hl-box table.kwd-tooltip-table td{{
  white-space: normal;
  max-width: 320px;
}}

</style>
""",
    unsafe_allow_html=True,
)

def render_cloud_login():
    """Authenticate before reading shared data; validate roles on every rerun."""
    repository = SupabaseRepository()
    if st.sidebar.button('로그아웃', key='cloud_logout'):
        session = st.session_state.get('auth_session')
        try:
            if session:
                repository.logout(session['access_token'])
        finally:
            st.session_state.clear()
        st.rerun()
    session = st.session_state.get('auth_session')
    if not session:
        _, login_col, _ = st.columns([1, 2, 1])
        with login_col:
            st.subheader('사내 계정 로그인')
            with st.form('cloud_login'):
                email = st.text_input('이메일')
                password = st.text_input('비밀번호', type='password')
                submit = st.form_submit_button('로그인')
            if submit:
                try:
                    st.session_state.auth_session = repository.login(email, password)
                    st.rerun()
                except (StorageError, PermissionError):
                    st.error('로그인에 실패했습니다. 계정과 연결 설정을 확인하세요.')
        st.stop()
    try:
        if session.get('expires_at', 0) < time.time() + 60:
            session = repository.refresh(session['refresh_token'])
            st.session_state.auth_session = session
        user = repository.user(session['access_token'])
        role = user.get('app_metadata', {}).get('role')
        if role not in {'admin', 'member'}:
            st.error('사내 앱 사용 권한이 없습니다. 관리자에게 문의하세요.')
            st.stop()
        st.session_state.cloud_user = user
        st.session_state.is_admin = role == 'admin'
        st.sidebar.caption(user.get('email', '로그인됨'))
    except (StorageError, PermissionError):
        st.error('로그인 세션을 확인할 수 없습니다. 로그아웃 후 다시 로그인하세요.')
        st.stop()


if cloud_enabled():
    try:
        render_cloud_login()
    except StorageError as e:
        st.error(str(e))
        st.stop()

try:
    init_state()
except (StorageError, PermissionError) as e:
    st.error(str(e))
    st.stop()
scan_existing_counters()

# Sidebar: 저장 경로 및 유틸 (초기화 UI는 제거됨)
st.sidebar.header("🗂 데이터 저장")
if cloud_enabled():
    st.sidebar.caption('Supabase 공유 저장소')
    if st.sidebar.button('최신 데이터 불러오기'):
        st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
        load_hits_log.clear()
else:
    st.sidebar.caption('CSV 개발 모드 — 공유 운영은 Supabase를 사용하세요.')


# --- 관리자 로그인 영역 (키워드 관리 탭 비공개용) ---
def render_admin_login():
    """사이드바에서 관리자 계정 로그인/로그아웃을 처리하고, st.session_state.is_admin 플래그를 유지합니다."""
    if cloud_enabled():
        return
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

    admin_user = None
    admin_password = None

    # 1) Streamlit secrets에서 시도
    try:
        admin_user = st.secrets.get("ADMIN_USER", None)
        admin_password = st.secrets.get("ADMIN_PASSWORD", None)
    except Exception:
        # secrets 미설정 환경 등 예외는 무시
        pass

    # 2) 환경 변수에서 보조로 시도 (깃허브 공개 저장소에 비밀번호를 하드코딩하지 않기 위함)
    if admin_user is None:
        admin_user = os.environ.get("ADMIN_USER")
    if admin_password is None:
        admin_password = os.environ.get("ADMIN_PASSWORD")

    with st.sidebar.expander("🔐 관리자 로그인", expanded=False):
        st.caption("키워드 관리 탭은 관리자 전용입니다. 관리자만 비밀번호를 알고 있어야 합니다.")
        input_id = st.text_input("관리자 ID", key="admin_id")
        input_pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw")

        c_login, c_logout = st.columns(2)
        with c_login:
            if st.button("로그인", key="admin_login"):
                ok = False
                if admin_password:
                    # ADMIN_USER가 설정되어 있으면 ID+PW 모두 검사, 아니면 PW만 검사
                    if admin_user:
                        ok = (input_id == admin_user and input_pw == admin_password)
                    else:
                        ok = (input_pw == admin_password)
                if ok:
                    st.session_state.is_admin = True
                    st.success("관리자 모드로 접속되었습니다.")
                else:
                    st.session_state.is_admin = False
                    st.error("관리자 인증에 실패했습니다. ID/비밀번호를 확인해주세요.")

        with c_logout:
            if st.button("로그아웃", key="admin_logout"):
                st.session_state.is_admin = False
                st.info("로그아웃 되었습니다.")

def is_admin() -> bool:
    """현재 세션이 관리자 모드인지 여부를 반환합니다."""
    return bool(st.session_state.get("is_admin", False))


render_admin_login()

if not cloud_enabled() and is_admin():
    new_path = st.sidebar.text_input('저장 경로 변경', value=st.session_state.storage_path)
    if st.sidebar.button('경로 적용'):
        st.session_state.storage_path = new_path
        st.session_state.kw_df = load_db(Path(new_path))
        scan_existing_counters()

MATCH_MODE_LABELS = {
    MATCH_MODES['exact']: '키워드 완전 일치',
    MATCH_MODES['similar']: '키워드 일부 일치',
    MATCH_MODES['partial']: '글자 수 매칭 - 탐색용',
}
MATCH_NORMALIZATION_OPTIONS = {
    'strip_bracket_notes': ('등록 키워드의 괄호 설명 제외',
        '등록 키워드에서 괄호 설명을 제외한 표현을 검색합니다.\n\n'
        '입력 원문의 괄호를 삭제하는 설정은 아닙니다.\n\n'
        '예시) 키워드 완전 일치 / 등록: `안티에이징(anti-aging)` / 입력: `안티에이징으로`\n\n'
        '- O · 옵션 켬 → `안티에이징` 검출\n'
        '- X · 옵션 끔 → 미검출'),
    'normalize_whitespace': ('띄어쓰기·줄바꿈 차이 허용',
        '공백·탭·줄바꿈 차이를 무시하고 비교합니다.\n\n'
        '끄면 공백과 줄바꿈을 그대로 비교합니다.\n\n'
        '예시) 키워드 완전 일치 / 등록: `피부보습` / 입력: `피부 보습`\n\n'
        '- O · 옵션 켬 → `피부 보습` 검출\n'
        '- X · 옵션 끔 → 미검출'),
    'ignore_case': ('영문 대소문자 무시',
        '영문 대소문자를 구분하지 않고 비교합니다.\n\n'
        '끄면 대소문자가 같아야 일치합니다.\n\n'
        '예시) 키워드 완전 일치 / 등록: `Spot` / 입력: `spot`\n\n'
        '- O · 옵션 켬 → `spot` 검출\n'
        '- X · 옵션 끔 → 미검출'),
    'normalize_symbols': ('설정된 기호를 공백으로 처리',
        '관리자 공통 목록에 있는 기호만 공백으로 바꿉니다.\n\n'
        '붙여 쓴 표현까지 비교하려면 띄어쓰기·줄바꿈 차이 허용도 켜세요.\n\n'
        '예시) 키워드 완전 일치 / 공통 기호: `&` / 등록: `피부 보습` / 입력: `피부&보습`\n\n'
        '- O · 옵션 켬 → `피부&보습` 검출\n'
        '- X · 옵션 끔 → 미검출'),
}
MATCH_MODE_HELP = {
    MATCH_MODES['exact']: '문장 안에서 등록된 표현을 찾습니다.\n\n키워드 매칭 옵션을 각각 선택하세요.\n\n조사·어미 허용 목록은 사용하지 않습니다.\n\n다른 단어 안의 표현도 검출할 수 있습니다.\n\n예시) 등록 `피부` → 입력 `피부과` → O (`피부` 검출)',
    MATCH_MODES['similar']: '등록 키워드의 앞·중간·뒷부분 중 연속된 2글자 이상이 일치하면 찾습니다.\n\n예시) 등록 `안티에이징` / 입력 `에이징 관리` → O · 키워드 `안티에이징` 검출',
    MATCH_MODES['partial']: '일부 일치와 같은 원리로 검색하며 최소 글자수를 직접 조절합니다.\n\n2글자로 설정하면 키워드 일부 일치와 결과가 같습니다.\n\n최소 글자수가 짧으면 관련 없는 결과가 늘어날 수 있습니다.',
}
MATCH_MODE_DETAILS = {
    MATCH_MODES['exact']: (
        '등록된 키워드 표현 전체를 문장 안에서 찾습니다.\n\n'
        '단어 경계를 강제하지 않아 다른 단어 안에 포함된 표현도 검출할 수 있습니다.\n\n'
        '예시) 등록 키워드: `피부`\n\n'
        '- O · `피부가 건조하다` → `피부` 검출\n'
        '- O · `피부과` → 다른 단어 안의 `피부` 검출\n'
        '- X · `피로` → `피부` 미검출\n\n'
        '괄호 설명·공백·대소문자·기호 차이는 키워드 매칭 옵션의 선택을 따릅니다.'),
    MATCH_MODES['similar']: (
        '등록 키워드의 앞·중간·뒷부분 중 연속된 일부 글자를 문장 어디서든 찾습니다.\n\n'
        '키워드의 첫 글자부터 일치하지 않아도 됩니다.\n\n'
        '최소 2글자를 기준으로 등록 키워드를 검출합니다.\n\n'
        '같은 위치에서는 가장 긴 일치 문구를 표시하며 포함된 모든 조각을 나열하지 않습니다.\n\n'
        '예시) 등록 키워드: `안티에이징`\n\n'
        '- O · 입력 `안티` → 키워드 `안티에이징` / 실제 일치 `안티`\n'
        '- O · 입력 `에이징 관리` → 키워드 `안티에이징` / 실제 일치 `에이징`\n'
        '- O · 입력 `티에이` → 키워드 `안티에이징` / 실제 일치 `티에이`\n'
        '- X · 입력 `안` → 최소 글자수 미달\n'
        '- X · 입력 `진정` → 미검출'),
    MATCH_MODES['partial']: (
        '키워드 일부 일치와 같은 검색 원리이며 최소 글자수를 직접 설정합니다.\n\n'
        '최소 2글자이면 키워드 일부 일치와 결과가 같습니다.\n\n'
        '글자수를 늘리면 짧은 조각으로 인한 결과를 줄일 수 있습니다.\n\n'
        '예시) 등록 키워드: `안티에이징`\n\n'
        '- O · 최소 2글자 / 입력 `안티` → 실제 일치 `안티`\n'
        '- X · 최소 3글자 / 입력 `안티` → 미검출\n'
        '- O · 최소 3글자 / 입력 `에이징` → 실제 일치 `에이징`\n'
        '- X · 최소 4글자 / 입력 `에이징` → 미검출'),
}


def invalidate_analysis_result():
    st.session_state['analysis_show'] = False


def render_matching_rules_summary(config):
    with st.expander('적용 중인 규칙 요약', expanded=False):
        selected = st.session_state.get('match_mode', MATCH_MODES[config.mode])
        st.caption('키워드 매칭 방식: ' + MATCH_MODE_LABELS.get(selected, '기존 변형 규칙 검색(API)'))
        if config.mode == 'partial':
            st.caption(f'최소 일치 글자수: {config.partial_min_len}글자')
        for name, (label, _) in MATCH_NORMALIZATION_OPTIONS.items():
            st.caption(label + ': ' + ('켜짐' if config.normalization_options()[name] else '꺼짐'))
        st.caption('키워드 매칭 옵션은 세 방식에 공통으로 적용합니다.\n\n일부 일치는 2글자 이상, 글자 수 매칭은 설정한 글자수 이상의 연속된 조각을 찾습니다.')
        if config.mode == 'similar':
            extras = config.ko_suffixes - _KO_SUFFIX_WHITELIST
            st.caption(f'뒤에 붙는 말 허용 목록: 기본 {len(_KO_SUFFIX_WHITELIST)}개 + 관리자 추가 {len(extras)}개')
            st.caption('허용 목록 외에 합성어 규칙도 함께 적용합니다.\n\n목록에 없는 말이 붙어도 검출될 수 있습니다.')
        else:
            st.caption('뒤에 붙는 말 허용 목록: 이 검사 방식에는 적용하지 않음')
        if config.normalization_options()['normalize_symbols']:
            st.caption('비교 시 처리할 기호: ' + (' · '.join(config.ignored_symbols) or '없음'))
        else:
            st.caption('기호 처리가 꺼져 있어 공통 기호 목록은 적용하지 않습니다.')
        st.caption('목록은 관리자 공통 설정입니다.\n\n분석 실행 시 저장된 최신 규칙을 다시 불러옵니다.')


def render_common_matching_rules():
    _require_admin()
    st.caption('저장한 규칙은 이후 분석부터 모든 사용자에게 적용됩니다.\n\n이번 분석 옵션은 분석하기 탭에서 선택합니다.')
    if message := st.session_state.pop('matching_rules_notice', None):
        st.success(message)
    version = st.session_state.get('matching_rules_editor_version', 0)

    with st.expander('기존 API용 조사·어미 허용 목록', expanded=False):
        st.caption('기존 similar API의 변형 규칙 검사에서만 참조합니다.\n\n현재 화면의 완전 일치와 일부 일치에는 적용하지 않습니다.')
        st.caption('기본 목록과 추가 목록을 합쳐 사용합니다.\n\n별도 합성어 규칙도 적용합니다.\n\n예시) 등록 키워드: `여드름`\n\n- O · 입력 `여드름에는` → `여드름` 검출\n- X · 입력 `뾰루지` → `여드름` 미검출')
        st.caption('으로·로·에는은 이미 기본 목록에 포함되어 있어 추가로 저장하지 않아도 됩니다.')
        st.write('기본 목록: ' + ', '.join(sorted(_KO_SUFFIX_WHITELIST)))
        with st.form('common_suffix_rules'):
            raw = st.text_area('추가로 허용할 말 — 한 줄에 하나 또는 쉼표로 구분',
                               value='\n'.join(st.session_state.get('ko_suffix_whitelist_extra', [])),
                               key=f'ui_suffix_extra_editor_{version}')
            save = st.form_submit_button('허용 목록 저장', key='btn_save_suffix_extra')
            reset = st.form_submit_button('추가 항목 모두 제거', key='btn_reset_suffix_extra')
        if save or reset:
            extra = [] if reset else list(dict.fromkeys(
                value.strip() for value in re.split(r'[\n,]+', raw)
                if value.strip() and value.strip() not in _KO_SUFFIX_WHITELIST))
            if save_suffix_whitelist_config(extra):
                st.session_state.ko_suffix_whitelist_extra = extra
                st.session_state.matching_rules_editor_version = version + 1
                st.session_state.matching_rules_notice = '허용 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.'
                st.rerun()
            st.error('저장하지 못했습니다. 연결과 권한을 확인하세요.')

    with st.expander('공백으로 처리할 기호 목록', expanded=False):
        st.caption('분석 화면에서 기호 처리를 켜면 이 목록의 기호를 공백으로 바꿉니다.\n\n띄어쓰기 차이 허용은 별도로 선택합니다.')
        st.caption('기호는 한 줄에 하나씩 입력하세요.\n\n쉼표(,)도 한 줄에 그대로 입력합니다.\n\n목록을 비우면 기존 기본값 / & , *가 적용됩니다.')
        with st.form('common_symbol_rules'):
            raw_symbols = st.text_area('비교 시 처리할 기호 — 한 줄에 하나',
                                       value='\n'.join(get_ignored_special_symbols()),
                                       key=f'ui_ignored_syms_editor_{version}')
            save = st.form_submit_button('기호 목록 저장', key='btn_save_ignored_syms')
            reset = st.form_submit_button('기본 기호로 복원', key='btn_reset_ignored_syms')
        if save or reset:
            symbols = (_DEFAULT_IGNORED_SPECIAL_SYMBOLS.copy() if reset else
                       list(dict.fromkeys(line.strip() for line in raw_symbols.splitlines() if line.strip())))
            if any(len(symbol) != 1 for symbol in symbols):
                st.error('각 줄에는 문자 하나만 입력하세요. 저장하지 않았습니다.')
            elif save_ignored_special_symbols_config(symbols):
                st.session_state.ignored_special_symbols = symbols
                st.session_state.matching_rules_editor_version = version + 1
                st.session_state.matching_rules_notice = '기호 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.'
                st.rerun()
            else:
                st.error('저장하지 못했습니다. 연결과 권한을 확인하세요.')


def render_user_management():
    """Load account data only on demand and keep it in this admin's session."""
    st.subheader('사용자 관리')
    st.caption('이 Supabase 프로젝트의 계정을 조회하고 앱 사용 역할을 변경합니다.\n\n한 페이지에 최대 50개 계정을 표시합니다.')
    token = st.session_state['auth_session']['access_token']
    repository = SupabaseRepository()
    page = st.number_input('페이지', min_value=1, max_value=100000, value=1,
                           step=1, key='user_admin_page')
    if st.button('사용자 목록 불러오기 / 새로고침', key='user_admin_load'):
        st.session_state.pop('managed_users', None)
        try:
            st.session_state.managed_users = repository.list_users(token, page=int(page))
            st.session_state.managed_users_page = int(page)
        except (StorageError, PermissionError, ValueError) as e:
            st.error(str(e))
            return
    users = st.session_state.get('managed_users')
    if users is None:
        st.info('사용자 목록을 불러와 역할을 변경하세요.')
        return
    if st.session_state.get('managed_users_page') != int(page):
        st.info('선택한 페이지의 사용자 목록을 다시 불러오세요.')
        return
    if not users:
        st.info('이 페이지에 계정이 없습니다.')
        return
    labels = {'member': '일반 사용자', 'admin': '관리자'}
    st.dataframe(pd.DataFrame([{
        '이메일': user['email'], '역할': labels.get(user['role'], '앱 권한 미지정'),
        '이메일 확인': '완료' if user['email_confirmed'] else '미완료',
    } for user in users]), hide_index=True, width='stretch')
    by_id = {user['id']: user for user in users}
    target_id = st.selectbox('변경할 계정', options=list(by_id),
                            format_func=lambda uid: by_id[uid]['email'] or uid,
                            key='user_admin_target')
    if target_id not in by_id:
        st.error('목록에서 계정을 선택하세요.')
        return
    target = by_id[target_id]
    st.caption('현재 역할: ' + labels.get(target['role'], '앱 권한 미지정'))
    own_account = target_id == st.session_state.cloud_user['id']
    if own_account:
        st.info('자신의 관리자 권한은 해제할 수 없습니다.')
    with st.form('user_admin_role_form'):
        role = st.selectbox('변경할 역할', options=['member', 'admin'],
                            index=1 if target['role'] == 'admin' else 0,
                            format_func=lambda value: labels[value],
                            key='user_admin_role_' + target_id, disabled=own_account)
        confirm = st.checkbox('선택한 계정의 역할 변경을 확인했습니다.', key='user_admin_confirm_' + target_id)
        submit = st.form_submit_button('역할 저장', disabled=own_account)
    if submit:
        if not confirm:
            st.warning('역할 변경 확인에 체크하세요.')
            return
        try:
            updated = repository.set_user_role(token, target_id, role, target['role'])
            # Keep the displayed snapshot consistent without resending a saved form.
            st.session_state.managed_users = [updated if u['id'] == target_id else u for u in users]
            st.session_state.user_admin_success = '역할을 저장했습니다. 해당 사용자는 로그아웃 후 다시 로그인하세요.'
            st.rerun()
        except (StorageError, PermissionError, ValueError) as e:
            st.error(str(e))


show_user_management = cloud_enabled() and is_admin()
tab_names = ["분석하기", "리포트(주간 Top N)"]
if is_admin():
    tab_names.append('키워드 관리')
if show_user_management:
    tab_names.append('사용자 관리')
tab1, tab3, *admin_tabs = st.tabs(tab_names)
user_tabs = admin_tabs[1:]

with tab1:
    # ① 텍스트 입력
    st.subheader("① 텍스트 입력")
    sample = "이 문장에는 필러와 안티에이징이라는 키워드가 포함되어 있습니다."
    text = st.text_area("분석할 텍스트", value=sample, height=180, max_chars=20000)

    st.markdown("---")
    # ②) 분석 실행
    st.subheader("② 분석 실행")
    with st.expander("사전 필터 (선택)", expanded=True):
        cf1, cf2, cf3 = st.columns([1,1,1])
        with cf1:
            db_cats = unique_values_from_db("상품카테고리")
            pre_cats = st.multiselect("상품카테고리", options=db_cats, key="pre_cats")
        with cf2:
            db_risks = unique_values_from_db("리스크 등급")
            pre_risks = st.multiselect("리스크 등급", options=db_risks, key="pre_risks")
        with cf3:
            match_mode = st.radio(
                "키워드 매칭 방식",
                list(MATCH_MODE_LABELS), index=0, key="match_mode",
                format_func=lambda value: MATCH_MODE_LABELS[value],
                on_change=invalidate_analysis_result,
                help='\n\n'.join(f'**{MATCH_MODE_LABELS[mode]}**\n\n{description}'
                                 for mode, description in MATCH_MODE_DETAILS.items()),
            )
            st.caption(MATCH_MODE_HELP[match_mode])
            if match_mode == MATCH_MODES['partial']:
                st.number_input("최소 일치 글자수", min_value=2, max_value=20,
                                value=int(st.session_state.get("partial_min_len", 2) or 2),
                                step=1, key="partial_min_len", persist_state="session",
                                on_change=invalidate_analysis_result,
                                help='예시) 등록 `안티에이징` / 입력 `에이징 관리가 필요하다`\n\n- O · 최소 3글자 → `에이징` 검출\n- X · 최소 4글자 → 미검출\n\n옵션에 따라 공백·기호를 처리한 뒤의 글자수를 기준으로 합니다.\n\n등록 키워드 자체가 최소 글자수보다 짧으면 검색하지 않습니다.')
            with st.expander('키워드 매칭 옵션', expanded=False):
                for name, (label, description) in MATCH_NORMALIZATION_OPTIONS.items():
                    st.checkbox(label, key=name, help=description, on_change=invalidate_analysis_result)
                st.caption('옵션을 변경하면 이전 결과를 숨깁니다.\n\n텍스트 분석하기를 눌러 새 조건으로 검사하세요.')
                if match_mode == MATCH_MODES['exact'] and not st.session_state.strip_bracket_notes:
                    st.info('현재는 괄호까지 포함한 등록명을 찾습니다.\n\n안티에이징(anti-aging)을 안티에이징으로에서도 찾으려면 괄호 설명 제외를 켜세요.')
            rules_summary = st.empty()
            with rules_summary.container():
                render_matching_rules_summary(_matching_config())

    if st.button("텍스트 분석하기", type="primary", key="btn_analyze"):
        try:
            # 항상 최신 키워드 DB 상태를 반영하기 위해 저장 경로에서 다시 로드
            try:
                st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
            except Exception as _e:
                st.warning(f"키워드 DB를 다시 불러오는 중 오류가 발생했습니다: {_e}")
            if st.session_state.kw_df.empty:
                st.info("키워드가 없습니다. 먼저 추가하세요.")
            else:
                config = _matching_config()
                if cloud_enabled():
                    config = load_matching_config(SupabaseRepository(), config)
                    st.session_state.ko_suffix_whitelist_extra = sorted(config.ko_suffixes - _KO_SUFFIX_WHITELIST)
                    st.session_state.ignored_special_symbols = list(config.ignored_symbols)
                with rules_summary.container():
                    render_matching_rules_summary(config)
                matches = match_text(
                    text, st.session_state.kw_df, config=config,
                    categories=st.session_state.get('pre_cats', []),
                    risks=st.session_state.get('pre_risks', []),
                )
                st.session_state.suffix_suggestions = {}

                if matches:
                    out = pd.DataFrame(
                        [
                            {
                                "kwd_no": m.kwd_no,
                                "키워드명": m.term,
                                "상품카테고리": m.category,
                                "리스크 등급": m.risk,
                                "리스크 등급별 세부 심의기준": m.detail,
                                "start": m.start,
                                "end": m.end,
                            }
                            for m in matches
                        ]
                    )
                    base_cols = ["kwd_no", "키워드명", "상품카테고리", "리스크 등급", "리스크 등급별 세부 심의기준"]
                    display_unique = out[base_cols].drop_duplicates(subset=["kwd_no"]).reset_index(drop=True)
                    display_unique = display_unique.sort_values(by="kwd_no", ascending=True).reset_index(drop=True)

                    # 누적 카운팅 + 마지막 출력일자 + 로그 기록
                    now_str = now_kst().strftime("%Y-%m-%d %H:%M:%S")
                    unique_kwds = display_unique["kwd_no"].dropna().astype(str).str.strip().tolist()
                    if unique_kwds and cloud_enabled():
                        result = {'analysis_id': str(uuid4()),
                                  'matches': [asdict(m) for m in matches],
                                  'unique_keywords': unique_kwds,
                                  'keyword_revision': st.session_state.cloud_revision,
                                  'offset_unit': 'unicode_codepoint',
                                  'end_exclusive': True, 'recorded': True}
                        fingerprint = hashlib.sha256(text.encode()).hexdigest()
                        SupabaseRepository().record_analysis(result['analysis_id'], fingerprint,
                            st.session_state.cloud_user['id'],
                            st.session_state.cloud_revision, result)
                        st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
                        load_hits_log.clear()
                    elif unique_kwds:
                        df = st.session_state.kw_df
                        try:
                            df_indexed = df.set_index("kwd_no")
                            for kw in unique_kwds:
                                if kw in df_indexed.index:
                                    try:
                                        prev = int(str(df_indexed.at[kw, "키워드 조회 수(누적카운트)"]).strip() or "0")
                                    except Exception:
                                        prev = 0
                                    df_indexed.at[kw, "키워드 조회 수(누적카운트)"] = str(prev + 1)
                                    df_indexed.at[kw, "마지막 출력일자"] = now_str
                            st.session_state.kw_df = df_indexed.reset_index()
                        except Exception:
                            for kw in unique_kwds:
                                idx_list = st.session_state.kw_df.index[st.session_state.kw_df["kwd_no"] == kw].tolist()
                                if idx_list:
                                    idx = idx_list[0]
                                    try:
                                        prev = int(str(st.session_state.kw_df.at[idx, "키워드 조회 수(누적카운트)"]).strip() or "0")
                                    except Exception:
                                        prev = 0
                                    st.session_state.kw_df.at[idx, "키워드 조회 수(누적카운트)"] = str(prev + 1)
                                    st.session_state.kw_df.at[idx, "마지막 출력일자"] = now_str
                        # CSV mode is local development only; analysis may update
                        # counters without granting keyword editing privileges.
                        sort_db_internal(st.session_state.kw_df)[get_db_cols()].to_csv(
                            Path(st.session_state.storage_path), index=False, encoding='utf-8-sig')
                        append_hits_log(unique_kwds)

                    out_buf = io.BytesIO()
                    out.to_csv(out_buf, index=False, encoding="utf-8-sig")

                    st.session_state['analysis_df_full'] = out
                    st.session_state['analysis_df_display_unique'] = display_unique
                    st.session_state['analysis_highlight_html'] = highlight_text(text, matches)
                    st.session_state['analysis_tooltip_map'] = HIGHLIGHT_TOOLTIP_MAP
                    st.session_state['analysis_count'] = len(display_unique)
                    st.session_state['analysis_text'] = text
                    st.session_state['analysis_csv_bytes'] = out_buf.getvalue()
                    st.session_state['analysis_show'] = True
                else:
                    st.session_state['analysis_show'] = False
                    st.session_state['analysis_df_full'] = None
                    st.session_state['analysis_df_display_unique'] = None
                    st.session_state['analysis_highlight_html'] = ''
                    st.session_state['analysis_count'] = 0
                    st.session_state['analysis_text'] = ''
                    st.session_state['analysis_csv_bytes'] = None
                    st.info("매칭된 키워드가 없습니다.")
        except Exception as e:
            import traceback as _tb
            st.error("오류 발생 (상세):")
            st.code(_tb.format_exc())

    _persist_df_full = st.session_state.get('analysis_df_full')
    _persist_df_unique = st.session_state.get('analysis_df_display_unique')
    _persist_highlight_html = st.session_state.get('analysis_highlight_html', '')
    _persist_tooltip_map = st.session_state.get('analysis_tooltip_map', {})
    _persist_count = st.session_state.get('analysis_count')
    _persist_csv = st.session_state.get('analysis_csv_bytes')

    if st.session_state.get('analysis_show') and _persist_df_full is not None:
        from streamlit import column_config as cc
        st.success(f"총 {_persist_count}건의 키워드가 발견되었습니다.")
        show_pos = st.checkbox("위치 인덱스(start/end) 보기", value=st.session_state.get("cb_pos", False), key="cb_pos")
        base_cols = ["kwd_no", "키워드명", "상품카테고리", "리스크 등급", "리스크 등급별 세부 심의기준"]
        column_cfg = {"리스크 등급별 세부 심의기준": cc.TextColumn()}

        # DB의 '모든 열'과 조인하여 전체 정보 표시
        try:
            merged_full = _persist_df_unique[["kwd_no"]].merge(
                st.session_state.kw_df[get_db_cols()], on="kwd_no", how="left"
            )
            merged_full = sort_for_display(merged_full)
        except Exception:
            merged_full = _persist_df_unique

        if show_pos:
            st.dataframe(_rename_fcol(_persist_df_full[base_cols + ["start", "end"]], width="stretch", column_config=column_cfg))
            st.markdown("**DB 전체 열 정보 (중복 제거)**")
            st.dataframe(_rename_fcol(merged_full), width="stretch")
        else:
            st.dataframe(_rename_fcol(merged_full), width="stretch")

        if _persist_csv is not None:
            st.download_button("분석 결과 CSV 다운로드", data=_persist_csv, file_name="analysis_results.csv", mime="text/csv", key="dl_analysis")


    st.subheader("하이라이트 미리보기")
    # 기존 하이라이트 HTML은 그대로 표시
    # Inject tooltip data + hover tooltip renderer (table-style) WITHOUT polluting preview body text
    _tt_map = st.session_state.get('analysis_tooltip_map', {}) or {}
    try:
        _tt_json = json.dumps(_tt_map, ensure_ascii=False)
    except Exception:
        _tt_json = "{}"
    st.markdown(
        """<script id='kwd-tooltip-data' type='application/json'>{_tt_json}</script>""",
        unsafe_allow_html=True,
    )
        # (재구성) 하이라이트 미리보기는 사용자 입력 원문(_persist_highlight_html)만 렌더링하고,
    # 툴팁(표 형태)은 JSON 데이터로 별도 주입한 뒤 JS로 body에 1개의 부유 툴팁을 띄웁니다.
    import json as _json_for_tt
    _tt_json = _json_for_tt.dumps(_persist_tooltip_map or {}, ensure_ascii=False)

    _component_html = """
    <div>
      <script id="kwd-tooltip-data" type="application/json">{_tt_json}</script>

      <style>
        .hl-box {{ border: 1px solid rgba(0,0,0,0.1); border-radius: 10px; padding: 10px; background: rgba(255,255,255,0.55); }}
        .hl-scroll {{ max-height: 520px; overflow: auto; line-height: 1.6; white-space: pre-wrap; word-break: break-word; tab-size: 4; }}
        /* floating tooltip (table-style) */
        #kwd-tt-float {{
          position: fixed;
          z-index: 2147483647;
          display: none;
          max-width: 92vw;
                    min-width: 420px;
                    width: min(720px, 92vw);
          height: 300px;
          max-height: 80vh;
          min-height: 180px;
          overflow: auto;
          resize: both;
          background: #f3f3f3;
          color: #111;
          border: 1px solid rgba(0,0,0,0.15);
          border-radius: 10px;
          box-shadow: 0 8px 22px rgba(0,0,0,0.18);
          padding: 10px 12px;
        }}
        #kwd-tt-float table {{ border-collapse: collapse; width: 100%; font-size: 12px; table-layout: fixed; }}
        #kwd-tt-float td, #kwd-tt-float th {{ border: 1px solid rgba(0,0,0,0.12); padding: 6px 8px; vertical-align: top; }
        #kwd-tt-float td { white-space: pre-wrap; overflow-wrap: anywhere; }}
        #kwd-tt-float th {{ background: rgba(0,0,0,0.04); white-space: nowrap; }}
        /* hint cursor */
        [data-kwd] {{ cursor: pointer; }}


/* Highlight colors (risk grades) */
.hl-box .hl-mark{
  padding:0;
  border-radius:2px;
  color:#000;
}
.hl-box .hl-risk1{background:#ffc9c9 !important;background-color:#ffc9c9 !important;}
.hl-box .hl-risk2{background:#a5d8ff !important;background-color:#a5d8ff !important;}
.hl-box .hl-risk3{background:#d0bfff !important;background-color:#d0bfff !important;}
.hl-box .hl-risk4{background:#b2f2bb !important;background-color:#b2f2bb !important;}
.hl-box .hl-risk5{background:#d8f5a2 !important;background-color:#d8f5a2 !important;}
.hl-box .hl-riskN{background:#ffd43b !important;background-color:#ffd43b !important;}

</style>

      <div class="hl-box"><div class="hl-scroll">{_persist_highlight_html}</div></div>
      <div id="kwd-tt-float" aria-hidden="true"></div>

      <script>
        (function(){{
          function getData(){{
            var node = document.getElementById('kwd-tooltip-data');
            if(!node) return {{}};
            try {{ return JSON.parse(node.textContent || '{{}}'); }} catch(e) {{ return {{}}; }}
          }}
          function esc(s){{
            return String(s)
              .replace(/&/g,'&amp;')
              .replace(/</g,'&lt;')
              .replace(/>/g,'&gt;')
              .replace(/"/g,'&quot;')
              .replace(/'/g,'&#39;');
          }}
          function buildTable(rows){{
            var html = '<table><tbody>';
            for(var i=0;i<rows.length;i++) {{
              var r = rows[i];
              if(!r || r.length < 2) continue;
              html += '<tr><th>' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td></tr>';
            }}
            html += '</tbody></table>';
            return html;
          }}

          var tt = document.getElementById('kwd-tt-float');
          var hideTimer = null;

          function hide(){{
            if(hideTimer) clearTimeout(hideTimer);
            hideTimer = setTimeout(function(){{ tt.style.display='none'; }}, 180);
          }}

          function showFor(target){{
            if(!target) return;
            var kwd = target.getAttribute('data-kwd');
            if(!kwd) return;

            if(hideTimer) {{ clearTimeout(hideTimer); hideTimer = null; }}

            var data = getData();
            var rows = data[kwd];
            if(!rows || !rows.length) {{
              rows = [['kwd_no', kwd], ['msg', 'tooltip 데이터가 없습니다.']];
            }}
            tt.innerHTML = buildTable(rows);

            tt.style.display = 'block';

            var rect = target.getBoundingClientRect();

            // keep inside viewport
            var bw = tt.offsetWidth;
            var bh = tt.offsetHeight;
            var vw = window.innerWidth;
            var vh = window.innerHeight;

            var spaceAbove = rect.top;
            var spaceBelow = vh - rect.bottom;

            // center align to kwd label
            var x = rect.left + (rect.width / 2) - (bw / 2);

            // Choose side with more space
            var y;
            if(spaceBelow >= spaceAbove){
              // below
              y = rect.bottom + 18;
              if(y + bh + 8 > vh) y = Math.max(8, vh - bh - 8);
            } else {
              // above
              y = rect.top - bh - 18;
              if(y < 8) y = 8;
            }

            // X clamp
            if(x + bw + 8 > vw) x = Math.max(8, vw - bw - 8);
            if(x < 8) x = 8;
            tt.style.left = x + 'px';
            tt.style.top  = y + 'px';
          }}

          function bind(){{
            var box = document.querySelector('.hl-box');
            if(!box) return false;
            var els = box.querySelectorAll('[data-kwd]');
            if(!els || !els.length) return false;

            for(var i=0;i<els.length;i++) {{
              var el = els[i];
              if(el.__kwd_tt_bound) continue;
              el.__kwd_tt_bound = true;

              el.addEventListener('mouseenter', function(ev){{ showFor(ev.currentTarget); }}, true);
              el.addEventListener('mouseleave', function(){{ hide(); }}, true);
            }}

            tt.addEventListener('mouseenter', function(){{ if(hideTimer){{ clearTimeout(hideTimer); hideTimer=null; }} }});
            tt.addEventListener('mouseleave', function(){{ hide(); }});
            return true;
          }}

          // Bind after render
          var tries = 0;
          var iv = setInterval(function(){{
            tries += 1;
            if(bind() || tries > 20) clearInterval(iv);
          }}, 250);
        }})();
      </script>
    </div>
    """

    # (재구성) HTML 템플릿에 실제 값을 주입하고, f-string 이스케이프용 중괄호를 원복
    _component_html = _component_html.replace('{_persist_highlight_html}', _persist_highlight_html)
    _component_html = _component_html.replace('{_tt_json}', _tt_json)
    _component_html = _component_html.replace('{{', '{').replace('}}', '}')

    components.html(_component_html, height=540, scrolling=True)


    # 새 창/네비게이션 없이 값만 주입: 하이라이트 HTML에서 kwd_no 수집 후 버튼으로 제공
    def _normalize_kw_label(s: str) -> str:
        try:
            s = str(s)
        except Exception:
            return ""
        # Normalize common invisible spaces (NBSP, zero-width space) to regular space, then strip
        for ch in ("\u00A0", "\u200B"):
            s = s.replace(ch, " ")
        return s.strip()

    _kwd_candidates = []
    try:
        import re as _re_for_kwd
        _raw_kwd_candidates = _re_for_kwd.findall(r"data-kwd='([^']+)'", _persist_highlight_html or "")
        _cleaned_candidates = []
        for _c in _raw_kwd_candidates:
            _n = _normalize_kw_label(_c)
            if _n:
                _cleaned_candidates.append(_n)
        _kwd_candidates = list(dict.fromkeys(_cleaned_candidates))
    except Exception:
        _kwd_candidates = []

        st.markdown("---")
    _base_df = st.session_state.kw_df.copy()
    _view_df = _base_df

    # -----------------------------
    # 🧰 리스트 상단 필터 바 (옵션 A)
    # - 표 위의 필터 바에서 조건을 선택하면 표가 즉시 좁혀집니다.
    # - 아무 필터도 선택하지 않으면 기존과 동일하게 전체가 표시됩니다.
    # -----------------------------
    def _reset_list_filters_tab1():
        # 위젯 입력값 초기화
        st.session_state["list_filter_search_tab1"] = ""

        st.session_state["list_filter_cat_tab1"] = []
        st.session_state["list_filter_risk_tab1"] = []
        st.session_state["list_filter_proof_tab1"] = []
        # '적용된' 필터값도 함께 초기화 (적용 버튼 기반 UX)
        st.session_state["list_filter_applied_search_tab1"] = ""
        st.session_state["list_filter_applied_kwdno_tab1_removed"] = ""
        st.session_state["list_filter_applied_cat_tab1"] = []
        st.session_state["list_filter_applied_risk_tab1"] = []
        st.session_state["list_filter_applied_proof_tab1"] = []
        st.session_state["list_filter_has_applied_tab1"] = False

    def _apply_list_filter_edits_tab1(edited_df: pd.DataFrame, original_df: pd.DataFrame) -> None:
        """리스트 필터 하단 표 편집 내용을 st.session_state.kw_df 및 DB 파일에 반영합니다.

        - edited_df: st.data_editor 결과 (사용자가 편집한 값)
        - original_df: 편집 전 원본 표 (현재 필터 상태에서의 원래 값)
        """
        if edited_df is None or edited_df.empty:
            return
        if original_df is None or original_df.empty:
            return

        base_df = st.session_state.kw_df.copy()
        db_cols = get_db_cols()

        if "kwd_no" not in base_df.columns or "kwd_no" not in original_df.columns:
            st.warning("kwd_no 컬럼이 없어 편집 내용을 반영할 수 없습니다.")
            return

        # 공통으로 존재하는 컬럼만 업데이트
        cols_to_update = [c for c in db_cols if c in edited_df.columns and c in base_df.columns]
        if not cols_to_update:
            return

        # 인덱스를 기준으로 원본/수정본을 1:1 매핑
        edited_norm = edited_df[cols_to_update].reset_index(drop=True).copy()
        original_norm = original_df.reset_index(drop=True).copy()

        for c in cols_to_update:
            try:
                edited_norm[c] = edited_norm[c].astype(str).str.strip()
            except Exception:
                pass
        if "kwd_no" in original_norm.columns:
            try:
                original_norm["kwd_no"] = original_norm["kwd_no"].astype(str).str.strip()
            except Exception:
                pass

        # kwd_no가 변경된 항목(old -> new) 수집 (조회 로그 업데이트 등에 사용)
        kwd_change_map = {}
        if "kwd_no" in cols_to_update and "kwd_no" in original_norm.columns:
            for i in range(len(edited_norm)):
                try:
                    old_no = str(original_norm.loc[i, "kwd_no"])
                    new_no = str(edited_norm.loc[i, "kwd_no"])
                except Exception:
                    continue
                if old_no and new_no and old_no != new_no:
                    kwd_change_map[old_no] = new_no

        # base_df 업데이트: 원본 kwd_no를 키로 사용해 행 단위로 덮어쓰기
        for i in range(len(edited_norm)):
            if "kwd_no" not in original_norm.columns:
                break
            try:
                old_no = str(original_norm.loc[i, "kwd_no"])
            except Exception:
                continue
            if not old_no:
                continue

            row_mask = base_df["kwd_no"].astype(str) == old_no
            if not row_mask.any():
                continue

            for c in cols_to_update:
                base_df.loc[row_mask, c] = edited_norm.loc[i, c]

        st.session_state.kw_df = base_df
        save_db(st.session_state.kw_df, Path(st.session_state.storage_path))

        # 조회 로그에도 kwd_no 변경 사항을 반영 (리포트 연동 유지)
        if kwd_change_map and not cloud_enabled():
            try:
                log_df = load_hits_log()
                if not log_df.empty and "kwd_no" in log_df.columns:
                    log_df["kwd_no"] = log_df["kwd_no"].astype(str)
                    for old_no, new_no in kwd_change_map.items():
                        log_df.loc[log_df["kwd_no"] == old_no, "kwd_no"] = new_no
                    overwrite_hits_log(log_df)
            except Exception as e:
                st.warning(f"조회 로그의 키워드 번호를 갱신하는 중 오류가 발생했습니다: {e}")


    st.markdown("#### 🧰 리스트 필터")

    # --------------------------------
    # 필터 적용 버튼 기반 UX
    # - 입력값을 바꿔도 즉시 표에 반영하지 않고,
    # - "필터 적용" 버튼을 눌렀을 때만 적용되도록 합니다.
    # --------------------------------

    # (Streamlit 경고 방지) key를 가진 위젯에는 default/value를 함께 주지 않습니다.
    # 대신 최초 1회만 session_state에 기본값을 세팅합니다.
    _init_defaults = {
        "list_filter_search_tab1": "",
        "list_filter_cat_tab1": [],
        "list_filter_risk_tab1": [],
        "list_filter_proof_tab1": [],
        "list_filter_edit_mode_tab1": False,
# 적용된 값(Apply 버튼 기준)
        "list_filter_applied_search_tab1": st.session_state.get("list_filter_applied_search_tab1", ""),
                "list_filter_applied_cat_tab1": st.session_state.get("list_filter_applied_cat_tab1", []),
        "list_filter_applied_risk_tab1": st.session_state.get("list_filter_applied_risk_tab1", []),
        "list_filter_applied_proof_tab1": st.session_state.get("list_filter_applied_proof_tab1", []),
}
    for _k, _v in _init_defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    with st.form("list_filter_form_tab1", clear_on_submit=False):
        f1, f2, f3, f4 = st.columns([3, 2, 2, 2])

        with f1:
            search_text = st.text_input(
                "키워드 검색",
                placeholder="키워드명 / 대체키워드 / kwd_no 검색",
                key="list_filter_search_tab1",
            )
        with f2:
            # 옵션 목록
            cat_opts = sorted([x for x in _base_df.get("상품카테고리", pd.Series([], dtype=str)).dropna().unique().tolist() if str(x).strip()])
            sel_cat = st.multiselect(
                "상품카테고리",
                options=cat_opts,
                key="list_filter_cat_tab1",
            )

        with f3:
            risk_opts = sorted([x for x in _base_df.get("리스크 등급", pd.Series([], dtype=str)).dropna().unique().tolist() if str(x).strip()])
            sel_risk = st.multiselect(
                "리스크 등급",
                options=risk_opts,
                key="list_filter_risk_tab1",
            )

        with f4:
            proof_opts = sorted([x for x in _base_df.get("증빙자료유형", pd.Series([], dtype=str)).dropna().unique().tolist() if str(x).strip()])
            sel_proof = st.multiselect(
                "증빙자료유형",
                options=proof_opts,
                key="list_filter_proof_tab1",
            )

        # 버튼 영역(요청: '필터 적용' 옆에 '필터 초기화' 고정 배치)
        b1, b2, _sp = st.columns([1, 1, 8])
        with b1:
            apply_clicked = st.form_submit_button(
                "필터 적용",
                key="btn_apply_list_filters_tab1",
                use_container_width=True,
            )
        with b2:
            # 같은 form 안에 두 버튼을 함께 배치해야 리런 시에도 위치가 틀어지지 않습니다.
            st.form_submit_button(
                "필터 초기화",
                key="btn_reset_list_filters_tab1",
                use_container_width=True,
                on_click=_reset_list_filters_tab1,
            )

    # '필터 적용' 시점에만 적용값을 저장
    if apply_clicked:
        st.session_state["list_filter_applied_search_tab1"] = st.session_state.get("list_filter_search_tab1", "")
        st.session_state["list_filter_applied_cat_tab1"] = st.session_state.get("list_filter_cat_tab1", [])
        st.session_state["list_filter_applied_risk_tab1"] = st.session_state.get("list_filter_risk_tab1", [])
        st.session_state["list_filter_applied_proof_tab1"] = st.session_state.get("list_filter_proof_tab1", [])
        st.session_state["list_filter_has_applied_tab1"] = True
        st.rerun()
    # Apply top filters (필터 적용 버튼을 눌렀을 때 저장된 값만 사용)
    _filtered_df = _view_df.copy()

    search_q = st.session_state.get("list_filter_applied_search_tab1", "")
    sel_cats = st.session_state.get("list_filter_applied_cat_tab1", [])
    sel_risks = st.session_state.get("list_filter_applied_risk_tab1", [])
    sel_evids = st.session_state.get("list_filter_applied_proof_tab1", [])
    # 키워드/대체키워드/kwd_no/리스크 등급별 세부 심의기준 검색
    if search_q and str(search_q).strip():
        # 쉼표로 여러 검색어를 입력하면 OR 조건으로 모두 포함 검색
        # 입력값에 괄호()가 포함되어도 검색되도록, 각 검색어의 앞뒤 괄호/공백을 제거하여 정규화
        raw_parts = [x for x in str(search_q).split(",") if str(x).strip()]
        q_list = []
        for _part in raw_parts:
            q = str(_part).strip()
            # (US087), US087), (US087 등도 모두 US087로 정규화
            q = re.sub(r"^[\s\(\)]+", "", q)
            q = re.sub(r"[\s\(\)]+$", "", q)
            if q:
                q_list.append(q)

        _kw = _filtered_df.get("키워드명", "").astype(str)
        _alt = _filtered_df.get("대체키워드", "").astype(str)
        _no = _filtered_df.get("kwd_no", "").astype(str)
        _detail = _filtered_df.get("리스크 등급별 세부 심의기준", "").astype(str)

        # 각 검색어별 mask를 만들고 OR로 합산
        mask_all = None
        for q in q_list:
            mask_q = (
                _kw.str.contains(q, case=False, na=False)
                | _alt.str.contains(q, case=False, na=False)
                | _no.str.contains(q, case=False, na=False)
                | _detail.str.contains(q, case=False, na=False)
            )
            mask_all = mask_q if mask_all is None else (mask_all | mask_q)

        if mask_all is not None:
            _filtered_df = _filtered_df[mask_all]

    # 멀티셀렉트 필터들
    if sel_cats:
        _filtered_df = _filtered_df[_filtered_df["상품카테고리"].astype(str).isin(sel_cats)]

    if sel_risks:
        _filtered_df = _filtered_df[_filtered_df["리스크 등급"].astype(str).isin(sel_risks)]

    if sel_evids:
        _filtered_df = _filtered_df[_filtered_df["증빙자료유형"].astype(str).isin(sel_evids)]
    # 리스트 보기/편집 모드 (관리자 전용 ON/OFF)
    edit_mode_effective = False
    mode_cols = st.columns([2, 8])
    with mode_cols[0]:
        if is_admin():
            st.checkbox(
                "리스트 편집 모드 (관리자 전용)",
                key="list_filter_edit_mode_tab1",
                help="ON: 아래 표에서 직접 값을 수정할 수 있습니다.\n\nOFF: 읽기 전용 뷰어 모드입니다.",
            )
            edit_mode_effective = bool(st.session_state.get("list_filter_edit_mode_tab1", False))
        else:
            # 관리자 로그인이 아니면 항상 뷰어 모드로 고정
            st.caption("리스트 편집 모드는 관리자 로그인 시에만 사용할 수 있습니다.")
            st.session_state["list_filter_edit_mode_tab1"] = False
            edit_mode_effective = False
    with mode_cols[1]:
        mode_label = "편집 모드(ON)" if edit_mode_effective else "뷰어 모드(읽기 전용)"
        st.caption(f"현재 표시된 항목: {len(_filtered_df)} / 전체: {len(_base_df)} · {mode_label}")

    _list_view_df = sort_for_display(_filtered_df[get_db_cols()])
    # --- 리스트 필터 표: '키워드명' / '대체키워드' 컬럼 폭 조정 (고정 + 데이터 길이 기반 자동) ---
    _kwd_col_config = None
    try:
        from streamlit import column_config as cc

        _cfg = {}
        # 1) 키워드명
        _kwd_series = _list_view_df.get("키워드명")
        _max_kwd_len = int(_kwd_series.astype(str).map(len).max()) if _kwd_series is not None and len(_list_view_df) else 0
        _kwd_width = "large" if _max_kwd_len >= 12 else "medium"
        _cfg["키워드명"] = cc.TextColumn(width=_kwd_width)

        # 2) 대체키워드
        _alt_series = _list_view_df.get("대체키워드")
        _max_alt_len = int(_alt_series.astype(str).map(len).max()) if _alt_series is not None and len(_list_view_df) else 0
        _alt_width = "large" if _max_alt_len >= 12 else "medium"
        _cfg["대체키워드"] = cc.TextColumn(width=_alt_width)

        _kwd_col_config = _cfg
    except Exception:
        _kwd_col_config = None

    if edit_mode_effective and is_admin():
        st.info("편집 모드: 셀을 수정한 뒤 반드시 아래 '변경사항 저장' 버튼을 눌러야 DB에 반영됩니다.")
        try:
            edited_df = st.data_editor(
                _list_view_df,
                key="list_filter_editor_tab1",
                use_container_width=True,
                column_config=_kwd_col_config or {},
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', '마지막 출력일자'] if cloud_enabled() else [],
            )
        except TypeError:
            # 구버전 Streamlit 호환: column_config 미지원
            edited_df = st.data_editor(
                _list_view_df,
                key="list_filter_editor_tab1",
                use_container_width=True,
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', '마지막 출력일자'] if cloud_enabled() else [],
            )
        save_clicked = st.button("변경사항 저장 (현재 필터된 행에만 적용)", key="btn_list_filter_save_tab1")
        if save_clicked:
            try:
                _apply_list_filter_edits_tab1(edited_df, _list_view_df)
                st.success("리스트 편집 내용이 저장되었습니다.")
            except Exception as e:
                st.error(f"리스트 편집 내용 저장 중 오류가 발생했습니다: {e}")
    else:
        try:
            st.dataframe(_rename_fcol(_list_view_df), width="stretch", column_config=_kwd_col_config or {})
        except TypeError:
            st.dataframe(_rename_fcol(_list_view_df), width="stretch")

    buf_bytes = io.BytesIO()
    st.session_state.kw_df[get_db_cols()].to_csv(buf_bytes, index=False, encoding="utf-8-sig")
    st.download_button("키워드 CSV 다운로드", data=buf_bytes.getvalue(), file_name="keywords_current.csv", mime="text/csv", key="dl_kw_current")

if is_admin():
    with admin_tabs[0]:
        st.subheader("키워드 관리 (편집/삭제/템플릿/업로드)")
        with st.expander('공통 분석 규칙 — 모든 사용자에게 적용', expanded=False):
            render_common_matching_rules()

        st.markdown("### 📂 키워드 업로드 (.csv / .xlsx)")
        col_u1, col_u2 = st.columns([2, 2])
        with col_u1:
            upload_mode = st.radio("업로드 모드", ["기존 유지 + 새로 추가", "완전 덮어쓰기"], horizontal=False, key="upload_mode")
        with col_u2:
            uploaded_file = st.file_uploader("키워드 템플릿 업로드", type=["csv", "xlsx"], key="uploader")

        if uploaded_file is not None:
            try:
                inc_df = None
                name = uploaded_file.name.lower()
                if name.endswith(".csv"):
                    raw = uploaded_file.read()
                    inc_df = read_csv_with_fallback_bytes(raw)
                elif name.endswith(".xlsx"):
                    raw = uploaded_file.read()
                    try:
                        inc_df = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
                    except Exception:
                        inc_df = read_xlsx_without_openpyxl(raw, header_row=1)
                else:
                    st.error("지원하지 않는 파일 형식입니다. CSV 또는 XLSX를 업로드하세요.")
                    inc_df = None

                if inc_df is not None:
                    inc_df = normalize_upload(inc_df)
                    # 기존 유틸 함수 폴백 처리
                    merged = None
                    added_cnt = 0
                    dedup_removed = 0
                    try:
                        inc_df = assign_missing_ids(inc_df)
                        mode = "merge" if upload_mode == "기존 유지 + 새로 추가" else "overwrite"
                        merged, added_cnt, dedup_removed = merge_or_overwrite(st.session_state.kw_df, inc_df, mode)
                    except NameError:
                        merged = pd.concat([st.session_state.kw_df, inc_df], ignore_index=True)
                    st.session_state.kw_df = merged
                    save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                    st.success(f"업로드 완료 — 추가 {added_cnt}건, (내부 중복제거 {dedup_removed}건) 저장됨.")
            except Exception as e:
                st.error(f"업로드 처리 중 오류: {e}")

        st.subheader("키워드 입력/관리")

        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1:
            term_in = st.text_input("키워드명 *", placeholder="예: 필러")
        with c2:
            db_cat_opts = unique_values_from_db("상품카테고리")
            cat_choice = st.selectbox("상품카테고리", db_cat_opts + ["(직접 입력)"])
        with c3:
            db_risk_opts = unique_values_from_db("리스크 등급")
            risk_choice = st.selectbox("리스크 등급", db_risk_opts)
        with c4:
            add_click = st.button("추가", type="primary", key="btn_add_row")

        c5, c6, c7 = st.columns([3, 3, 3])
        with c5:
            detail_choice = st.selectbox("리스크 등급별 세부 심의기준", _dropdown_with_input_option(st.session_state.opt_details))
        with c6:
            db_evid_opts = unique_values_from_db("증빙자료유형")
            evidence_choice = st.selectbox("증빙자료유형", _dropdown_with_input_option(db_evid_opts))
        with c7:
            alt_choice = st.selectbox("대체키워드", _dropdown_with_input_option(st.session_state.opt_alt_terms))

        new_cat = new_detail = new_evid = new_alt = ""
        new_kwd = ""

        if cat_choice == "(직접 입력)":
            cols_nc = st.columns([2,1])
            with cols_nc[0]:
                new_cat = st.text_input("새 카테고리 입력", key="new_cat_input")
            with cols_nc[1]:
                new_kwd = st.text_input("키워드NO (선택, 예: P001)", key="new_kwd_input")

        if detail_choice == "(직접 입력)":
            new_detail = st.text_input("새 세부 심의기준 입력", key="new_detail_input")
        if evidence_choice == "(직접 입력)":
            new_evid = st.text_input("새 증빙자료유형 입력", key="new_evid_input")
        if alt_choice == "(직접 입력)":
            new_alt = st.text_input("새 대체키워드 입력", key="new_alt_input")

        if add_click:
            if not term_in.strip():
                st.warning("키워드명은 필수입니다.")
            else:
                category = new_cat.strip() if cat_choice == "(직접 입력)" and new_cat.strip() else cat_choice
                detail = new_detail.strip() if detail_choice == "(직접 입력)" and new_detail.strip() else detail_choice
                evidence = new_evid.strip() if evidence_choice == "(직접 입력)" and new_evid.strip() else evidence_choice
                alt_term = new_alt.strip() if alt_choice == "(직접 입력)" and new_alt.strip() else alt_choice

                if category == "(직접 입력)" or detail == "(직접 입력)" or evidence == "(직접 입력)" or alt_term == "(직접 입력)":
                    st.warning("새 항목을 입력했으면 값을 채우거나 기존 목록에서 선택하세요.")
                else:
                    kwd = None
                    _kw = (st.session_state.get("new_kwd_input", "") or "").strip()
                    if _kw:
                        m = _custom_kwd_pattern.match(_kw)
                        if m:
                            pfx, num = m.group(1).upper(), m.group(2)
                            kwd = f"{pfx}{int(num):0{len(num)}d}"
                    if kwd is None:
                        kwd = next_kwd_no(category)
                    now_str = now_kst().strftime("%Y-%m-%d %H:%M:%S")
                    _existing_kwds = st.session_state.kw_df['kwd_no'].astype(str).str.upper().tolist()
                    if str(kwd).upper() in _existing_kwds:
                        st.warning(f"{kwd}은(는) 이미 존재하는 키워드 번호입니다. 다른 번호를 지정해 주세요.")
                        st.stop()

                    row = {
                        "kwd_no": kwd,
                        "키워드명": term_in.strip(),
                        "상품카테고리": category,
                        "리스크 등급": risk_choice,
                        "리스크 등급별 세부 심의기준": detail,
                        "증빙자료유형": evidence,
                        "대체키워드": alt_term,
                        "키워드 조회 수(누적카운트)": "0",
                        "마지막 출력일자": "",

                        "키워드 등록일자": now_str
                    }
                    st.session_state.kw_df = pd.concat([st.session_state.kw_df, pd.DataFrame([row])], ignore_index=True)
                    save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                    st.success(f"[{kwd}] '{term_in}' 추가 및 저장됨")

                    # 저장 성공 후에만 드롭다운 옵션에 신규 값 추가 및 JSON 저장
                    if cat_choice == "(직접 입력)" and new_cat.strip() and new_cat not in st.session_state.opt_categories:
                        st.session_state.opt_categories.append(new_cat.strip())
                        save_dropdown_config()
                    if detail_choice == "(직접 입력)" and new_detail.strip() and new_detail not in st.session_state.opt_details:
                        st.session_state.opt_details.append(new_detail.strip())
                        save_dropdown_config()
                    if evidence_choice == "(직접 입력)" and new_evid.strip() and new_evid not in st.session_state.opt_evidences:
                        st.session_state.opt_evidences.append(new_evid.strip())
                        save_dropdown_config()
                    if alt_choice == "(직접 입력)" and new_alt.strip() and new_alt not in st.session_state.opt_alt_terms:
                        st.session_state.opt_alt_terms.append(new_alt.strip())
                        save_dropdown_config()

        with st.expander("드롭다운 값 삭제 (관리자)"):
            colm1, colm2 = st.columns([2,3])

            with colm1:
                target_list = st.selectbox("대상 목록", [
                    "상품카테고리", "리스크 등급", "리스크 등급별 세부 심의기준", "증빙자료유형", "대체키워드"
                ], key="del_list")

            with colm2:
                options_map = {
                    "상품카테고리": st.session_state.opt_categories,
                    "리스크 등급": st.session_state.opt_risks,
                    "리스크 등급별 세부 심의기준": st.session_state.opt_details,
                    "증빙자료유형": st.session_state.opt_evidences,
                    "대체키워드": st.session_state.opt_alt_terms,
                }

                current = options_map.get(target_list, [])
                to_del = st.selectbox("삭제할 값 선택", current, key="del_value") if current else None

            if to_del is not None and st.button("삭제", key="btn_del_value"):
                st.session_state['__del_request__'] = (target_list, to_del)

            if st.session_state.get('__del_request__'):
                tgt, val = st.session_state['__del_request__']
                st.warning(f"{tgt}에서 '{val}' 값을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")

                cols_confirm = st.columns([1,1,6])

                if cols_confirm[0].button("예, 삭제", key="btn_del_confirm"):
                    lst = options_map[tgt]
                    try:
                        lst.remove(val)
                        save_dropdown_config()  # JSON 파일에 저장
                        st.success(f"삭제 완료: {tgt} → {val}")
                    except ValueError:
                        st.info("이미 삭제되었거나 존재하지 않습니다.")
                    st.session_state['__del_request__'] = None

                if cols_confirm[1].button("아니오", key="btn_del_cancel"):
                    st.session_state['__del_request__'] = None

        st.markdown("---")

        mode = st.radio("편집 모드 선택", ["드롭다운(제한 입력)", "자유 입력"], horizontal=True, key="edit_mode")
        base_df = sort_for_display(st.session_state.kw_df[get_db_cols()].copy())

        if mode == "드롭다운(제한 입력)":
            from streamlit import column_config as cc
            # Build union option lists including existing DB values
            db_cat_opts = unique_values_from_db("상품카테고리")
            db_risk_opts = unique_values_from_db("리스크 등급")
            db_detail_opts = unique_values_from_db(RAW_F_COL)
            db_alt_opts = unique_values_from_db("대체키워드")
            detail_opts = _dropdown_with_input_option(list(set((st.session_state.opt_details or []) + (db_detail_opts or []))))
            alt_opts = _dropdown_with_input_option(list(set((st.session_state.opt_alt_terms or []) + (db_alt_opts or []))))
            risk_opts = list(set((st.session_state.opt_risks or []) + (db_risk_opts or []))) or st.session_state.opt_risks
            cat_opts = list(set((st.session_state.opt_categories or []) + (db_cat_opts or []))) or st.session_state.opt_categories
            edited_df = st.data_editor(_rename_fcol(
                base_df),
                column_config={
                    "상품카테고리": cc.SelectboxColumn(options=cat_opts, required=False),
                    "리스크 등급": cc.SelectboxColumn(options=risk_opts, required=False),
                    DISPLAY_F_COL: cc.SelectboxColumn(options=detail_opts, required=False, label=DISPLAY_F_COL),
                    "증빙자료유형": cc.SelectboxColumn(options=st.session_state.opt_evidences, required=False),
                    "대체키워드": cc.SelectboxColumn(options=alt_opts, required=False),
                },
                width="stretch",
                num_rows="fixed" if cloud_enabled() else "dynamic",
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', '마지막 출력일자'] if cloud_enabled() else [],
                key="editor_dropdown",
            )
        else:
            edited_df = st.data_editor(_rename_fcol(base_df), width="stretch",
                num_rows="fixed" if cloud_enabled() else "dynamic", key="editor_free",
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', '마지막 출력일자'] if cloud_enabled() else [])

        csave, cdel, ctmpl = st.columns([1, 1, 2])
        with csave:
            if st.button("변경사항 저장", type="primary", key="btn_save_edits"):
                edited_df = edited_df.fillna("")
                # --- Map UI display column back to raw DB column before slicing ---
                try:
                    if DISPLAY_F_COL in edited_df.columns and RAW_F_COL not in edited_df.columns:
                        edited_df[RAW_F_COL] = edited_df[DISPLAY_F_COL]
                        try:
                            edited_df = edited_df.drop(columns=[DISPLAY_F_COL])
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    st.session_state.kw_df = edited_df[get_db_cols()].copy()
                except KeyError:
                    missing = [c for c in get_db_cols() if c not in edited_df.columns]
                    for c in missing:
                        edited_df[c] = ""
                    st.session_state.kw_df = edited_df[get_db_cols()].copy()

                save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                st.success("수정 내용 저장 완료")

        with cdel:
            del_targets = st.multiselect(
                "삭제할 항목 선택 (kwd_no 기준)",
                options=st.session_state.kw_df["kwd_no"].tolist(),
                key="del_targets"
            )
            if st.button("선택 삭제", type="secondary", key="btn_delete_rows"):
                if not del_targets:
                    st.warning("삭제할 항목을 선택하세요.")
                else:
                    st.session_state.kw_df = st.session_state.kw_df[~st.session_state.kw_df["kwd_no"].isin(del_targets)].reset_index(drop=True)
                    save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                    st.success(f"{len(del_targets)}건 삭제 완료")

        with ctmpl:
            st.markdown("**업로드 템플릿 다운로드**")
            tmpl_csv_buf = io.BytesIO()
            pd.DataFrame(columns=DB_COLS).to_csv(tmpl_csv_buf, index=False, encoding="utf-8-sig")
            st.download_button("CSV 템플릿 다운로드", data=tmpl_csv_buf.getvalue(), file_name="keyword_template.csv", mime="text/csv", key="dl_tmpl_csv")
            try:
                tmpl_xlsx_buf = io.BytesIO()
                with pd.ExcelWriter(tmpl_xlsx_buf) as writer:
                    pd.DataFrame(columns=DB_COLS).to_excel(writer, sheet_name="keywords_template", index=False)
                st.download_button("엑셀 템플릿 다운로드", data=tmpl_xlsx_buf.getvalue(), file_name="keyword_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_tmpl_xlsx")
            except Exception as e:
                st.info(f"엑셀 템플릿은 현재 환경에 openpyxl/xlsxwriter가 없어 CSV 템플릿으로 대체합니다. (세부: {e})")

        st.caption(f"현재 저장된 항목: {len(st.session_state.kw_df)}")
        st.dataframe(_rename_fcol(sort_for_display(st.session_state.kw_df[get_db_cols()])), width="stretch")


with tab3:
    st.subheader("📈 리포트 — 최근 7일 Top N")

    # 리포트 본문
    log_df = load_hits_log()
    if log_df.empty:
        st.info("조회 로그가 아직 없습니다. 분석을 몇 번 실행하면 리포트가 생성됩니다.")
    else:
        col_r1, col_r2 = st.columns([1,1])
        with col_r1:
            top_n = st.number_input("Top N", min_value=1, max_value=100, value=10, step=1, key="report_topn")
        with col_r2:
            end_dt = now_kst()
            start_dt = end_dt - timedelta(days=7)
            st.write(f"기간: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            _tmp = log_df.copy()
            _tmp["ts_dt"] = pd.to_datetime(_tmp["ts"], errors="coerce")
            mask = (_tmp["ts_dt"] >= start_dt) & (_tmp["ts_dt"] <= end_dt)
            week_df = _tmp.loc[mask]
            agg = week_df.groupby("kwd_no").size().reset_index(name="최근7일_조회수")
            agg = agg.sort_values("최근7일_조회수", ascending=False).head(top_n)

            report = agg.merge(st.session_state.kw_df[get_db_cols()], on="kwd_no", how="left")
            report = report.sort_values(["최근7일_조회수","kwd_no"], ascending=[False, True], kind="mergesort")

            # ---- Column order tweak: place '최근7일_조회수' right after '대체키워드' ----
            try:
                cols = list(report.columns)
                if "최근7일_조회수" in cols:
                    cols.remove("최근7일_조회수")
                    if "대체키워드" in cols:
                        idx = cols.index("대체키워드") + 1
                    elif "증빙자료유형" in cols:
                        idx = cols.index("증빙자료유형") + 1
                    else:
                        idx = len(cols)
                    cols.insert(idx, "최근7일_조회수")
                    report = report[cols]
            except Exception:
                pass
            # ----------------------------------------------------------------------

            # ---- Right align numeric columns ----
            align_cols = [c for c in ["최근7일_조회수", "키워드 조회 수(누적카운트)"] if c in report.columns]
            styled = report.style.set_properties(**{"text-align": "right"}, subset=align_cols)

            st.dataframe(_rename_fcol(styled), width="stretch")
            rep_buf = io.BytesIO()
            report.to_csv(rep_buf, index=False, encoding="utf-8-sig")
            st.download_button("리포트 CSV 다운로드 (최근 7일 Top N)", data=rep_buf.getvalue(), file_name="weekly_topN_report.csv", mime="text/csv", key="dl_week_report")
        except Exception as e:
            st.error(f"리포트 생성 중 오류: {e}")

    # ------------------------------
    # 🔁 조회 수 초기화 (CSV 다운로드 영역 '아래'로 이동)
    # ------------------------------
    if is_admin():
        st.markdown("---")
        st.markdown("### 🔁 조회 수 초기화")

        # 전체 초기화: DB의 누적카운트=0, 마지막 출력일자 공백 (로그는 유지 — 기존 동작 유지)
        col_z1, col_z2 = st.columns([1,1])
        with col_z1:
            confirm_reset_all = st.checkbox("전체 조회 수를 0으로 초기화하고 '마지막 출력일자'를 비우기", value=False, key="report_reset_ck")
            if st.button("전체 초기화 실행", disabled=not confirm_reset_all or not is_admin(), key="report_reset_btn"):
                _require_admin()
                try:
                    if cloud_enabled():
                        SupabaseRepository().reset_counts()
                        st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
                        st.success('전체 초기화 완료 (로그 유지)')
                        st.stop()
                    if "키워드 조회 수(누적카운트)" in st.session_state.kw_df.columns:
                        st.session_state.kw_df["키워드 조회 수(누적카운트)"] = "0"
                    if "마지막 출력일자" in st.session_state.kw_df.columns:
                        st.session_state.kw_df["마지막 출력일자"] = ""
                    save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                    st.success("전체 초기화 완료 (로그 파일은 유지됩니다)")
                except Exception as e:
                    st.error(f"초기화 실패: {e}")

        # 최근 7일 초기화: 로그에서 최근 7일 기록만 삭제 (DB 누적카운트는 건드리지 않음)
        with col_z2:
            confirm_reset_week = st.checkbox("최근 7일 조회수 초기화 (로그에서 최근 7일 기록 삭제)", value=False, key="report_reset7_ck")
            if st.button("최근 7일 초기화 실행", disabled=not confirm_reset_week or not is_admin(), key="report_reset7_btn"):
                _require_admin()
                try:
                    if cloud_enabled():
                        removed = SupabaseRepository().reset_week()
                        load_hits_log.clear()
                        st.success(f'최근 7일 기록 {removed}건을 리포트에서 제외했습니다.')
                        st.stop()
                    log_df2 = load_hits_log()
                    if log_df2.empty:
                        st.info("삭제할 로그가 없습니다.")
                    else:
                        end_dt2 = now_kst()
                        start_dt2 = end_dt2 - timedelta(days=7)
                        log_df2["ts_dt"] = pd.to_datetime(log_df2["ts"], errors="coerce")
                        before_cnt = len(log_df2)
                        # keep records outside the last 7 days or with NaT (safety)
                        keep_mask = (log_df2["ts_dt"].isna()) | (log_df2["ts_dt"] < start_dt2) | (log_df2["ts_dt"] > end_dt2)
                        new_log = log_df2.loc[keep_mask, ["ts","kwd_no"]].reset_index(drop=True)
                        overwrite_hits_log(new_log)
                        removed = before_cnt - len(new_log)
                        st.success(f"최근 7일 로그 {removed}건 삭제 완료")
                except Exception as e:
                    st.error(f"최근 7일 초기화 실패: {e}")

if user_tabs:
    with user_tabs[0]:
        if message := st.session_state.pop('user_admin_success', None):
            st.success(message)
        render_user_management()

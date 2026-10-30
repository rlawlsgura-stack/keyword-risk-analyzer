# -*- coding: utf-8 -*-
"""
Keyword Risk Analyzer (FIXED325 - current release)
- Based on v97
- NEW: 드롭다운 목록을 JSON 파일로 영구 저장하여 재부팅 후에도 유지
- KEEP: 모든 기존 기능 유지 (조회 수 카운팅, 리포트, 최근 7일 초기화 등)
"""
from __future__ import annotations
import os
import sys
import unicodedata

# PaddleX reads this flag while its package is imported. Set it before loading
# Streamlit, pandas, or application modules so reruns cannot trigger a second
# eager repository initialization.
os.environ["PADDLE_PDX_EAGER_INIT"] = "False"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
# Streamlit reruns keep imported modules in sys.modules. If PaddleX's flags
# module was loaded earlier, update its cached value as well as the environment.
_paddlex_flags = sys.modules.get("paddlex.utils.flags")
if _paddlex_flags is not None:
    _paddlex_flags.EAGER_INITIALIZATION = False

from typing import List, Tuple, Set, Optional
import pandas as pd
from matching_engine import (
    DB_COLS, Match2, MatchingConfig, MATCH_MODES,
    _KO_SUFFIX_WHITELIST, _DEFAULT_IGNORED_SPECIAL_SYMBOLS,
    find_matches as _engine_find_matches,
    find_matches_nlp as _engine_find_matches_nlp,
)
import streamlit as st
import requests

# Global tooltip data for highlight preview (kept separate from preview HTML)
HIGHLIGHT_TOOLTIP_MAP: dict = {}

_RECOVERY_COMPONENT_KEY = 'cloud_password_recovery'
_RECOVERY_COMPONENT = st.components.v2.component(
    'kra_password_recovery_hash',
    html='<span></span>',
    js="""
export default function (component) {
  const { data, setStateValue } = component
  const hash = window.location.hash || ''
  if (data.clear_url) {
    if (hash) history.replaceState(null, '', window.location.pathname + window.location.search)
  } else if (hash && hash !== (data.known_hash || '') && hash.includes('access_token=')) {
    setStateValue('hash', hash)
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}
""",
)

_AUTH_SESSION_COMPONENT_KEY = 'cloud_auth_session_storage'
_AUTH_SESSION_COMPONENT = st.components.v2.component(
    'kra_auth_session_storage',
    html='<span></span>',
    js="""
export default function (component) {
  const { data, setStateValue } = component
  const key = 'kra-auth-refresh-token'
  try {
    if (data.action === 'clear') {
      sessionStorage.removeItem(key)
      if (!data.checked || data.known_refresh_token) {
        setStateValue('refresh_token', '')
        setStateValue('checked', true)
      }
    } else if (data.action === 'save') {
      if (data.refresh_token && sessionStorage.getItem(key) !== data.refresh_token) {
        sessionStorage.setItem(key, data.refresh_token)
      }
    } else {
      const token = sessionStorage.getItem(key) || ''
      if (!data.checked || token !== (data.known_refresh_token || '')) {
        setStateValue('refresh_token', token)
        setStateValue('checked', true)
      }
    }
  } catch (error) {
    setStateValue('storage_error', true)
    setStateValue('checked', true)
  }
}
""",
)


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
import logging
from difflib import SequenceMatcher
import hashlib
import time
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit, urlunsplit
from dataclasses import asdict
from xml.etree import ElementTree as ET
from pathlib import Path
APP_VERSION = "FIXED325"
from app_config import configure, cloud_enabled
# Local Streamlit runs execute this file directly, so invalidate a stale
# repository module retained by an already-running Streamlit process.
_cached_repository = sys.modules.get('repository')
if (_cached_repository is not None
        and not hasattr(getattr(_cached_repository, 'SupabaseRepository', None),
                        'reject_unmatched_registration_requests')):
    sys.modules.pop('repository', None)
from repository import SupabaseRepository, StorageError, ConflictError
from request_notifications import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    is_notification_configured,
    send_keyword_request_email,
)
from service import load_matching_config
from approved_matching import match_text, validate_expressions, SETTING_NAME

def _selectable_dataframe(*args, **kwargs):
    kwargs.setdefault("on_select", "rerun")
    kwargs.setdefault("selection_mode", "multi-row")
    return st.dataframe(*args, **kwargs)


try:
    configure(dict(st.secrets))
except FileNotFoundError:
    configure()


def _require_admin():
    if not st.session_state.get('is_admin', False):
        st.error('관리자만 데이터를 변경할 수 있습니다.')
        st.stop()



def _require_ocr_access():
    """OCR registration is available to authenticated members and admins."""
    if st.session_state.get('is_admin', False):
        return
    user = st.session_state.get('cloud_user') or {}
    role = (user.get('app_metadata') or {}).get('role')
    if cloud_enabled() and role == 'member':
        return
    _require_admin()

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
LAST_HIT_COL = "마지막 출력일자"
LAST_SEARCH_LABEL = "마지막 검색일자"
UI_COLUMN_LABELS = {RAW_F_COL: DISPLAY_F_COL, LAST_HIT_COL: LAST_SEARCH_LABEL}

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
    """화면에 표시할 컬럼명만 바꾸고 원본 데이터는 유지합니다."""
    try:
        import pandas as _pd
        # Styler가 들어오면 원본 DataFrame을 가져와 컬럼만 바꾸고 다시 스타일 적용
        if hasattr(df, 'to_excel') and hasattr(df, 'style'):
            # DataFrame (가급적 이 분기로)
            return df.rename(columns=UI_COLUMN_LABELS)
        # pandas Styler 처리
        if getattr(df, '__class__', None).__name__ == 'Styler':
            base = getattr(df, 'data', None)
            if base is not None and hasattr(base, 'rename'):
                return base.rename(columns=UI_COLUMN_LABELS).style
        # 그 외 객체도 columns 속성이 있으면 시도
        if hasattr(df, 'rename') and hasattr(df, 'columns'):
            return df.rename(columns=UI_COLUMN_LABELS)
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
    registration_col = "키워드 등록일자"
    legacy_registration_col = "키워드등록일자"
    if registration_col not in df.columns:
        df[registration_col] = ""
    if legacy_registration_col in df.columns:
        current_dates = df[registration_col].fillna("").astype(str).str.strip()
        legacy_dates = df[legacy_registration_col].fillna("").astype(str).str.strip()
        missing_current = current_dates.eq("")
        df.loc[missing_current, registration_col] = legacy_dates[missing_current]
        df = df.drop(columns=[legacy_registration_col])
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

def save_db(df: pd.DataFrame, path: Path, *, allow_ocr_member: bool = False) -> None:
    if allow_ocr_member:
        _require_ocr_access()
    else:
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
    # Keep legacy and canonical registration-date labels merged in existing sessions too.
    st.session_state.kw_df = _ensure_counter_columns(st.session_state.kw_df)
    st.session_state.db_cols_order = list(st.session_state.kw_df.columns)

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
        "마지막 검색일자": LAST_HIT_COL,
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
        mode=selected_mode,
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
        registration_columns = {"키워드등록일자", "키워드 등록일자"}
        registration_date = ""
        for col in ("키워드 등록일자", "키워드등록일자"):
            value = row.get(col, "")
            try:
                if pd.isna(value):
                    continue
            except Exception:
                pass
            if str(value).strip():
                registration_date = str(value).strip()
                break
        for col, val in row.items():
            if str(col).strip() in registration_columns:
                continue
            try:
                if pd.isna(val):
                    val = ""
            except Exception:
                pass
            sval = str(val).strip()
            if not sval and col != LAST_HIT_COL:
                continue
            tooltip_label = "리스크 등급별 세부 심의기준" if str(col) == RAW_F_COL else UI_COLUMN_LABELS.get(str(col), str(col))
            out.append((tooltip_label, sval))
        last_date_row = next((i for i, item in enumerate(out) if item[0] == LAST_SEARCH_LABEL), None)
        registration_row = ("키워드 등록일자", registration_date)
        out.insert(last_date_row + 1 if last_date_row is not None else len(out), registration_row)
        if not out:
            out = [("kwd_no", kwd_no)]
        return out
    except Exception as e:
        return [("kwd_no", kwd_no), ("msg", f"tooltip 데이터 생성 오류: {e}")]


def highlight_text(text: str, matches: List[Match2], config: MatchingConfig = None,
                  approved_partials=None) -> str:
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
            info = {'seg': seg, 'ids_raw': [], 'risk_map': {}, 'match_records': []}
            spans[key] = info

        if m.kwd_no:
            info['ids_raw'].append(m.kwd_no)
            norm = _extract_kwd_token(m.kwd_no)
            info['risk_map'][norm] = _risk_grade(m.risk)
            info['match_records'].append((norm, m, seg))

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
            previous['match_records'].extend(info['match_records'])
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

        # 각 번호는 별도 항목으로 감싸, 번호만 묶음 단위로 숨길 수 있게 합니다.
        frag_parts = []
        detected_target = seg.strip()
        for i, raw in enumerate(ids_raw):
            head, token, tail = _split_around_token(raw)
            norm = _extract_kwd_token(raw) or (token or str(raw).strip())
            toggle_key = json.dumps([norm, detected_target], ensure_ascii=False, separators=(',', ':'))

            g = risk_map.get(norm, 0)
            color = text_colors.get(g, 'inherit')
            # 키워드 번호 클릭 시 별도 팝업에 상세 정보를 표시합니다.
            # Keep per-occurrence match evidence with the DB row details.
            tooltip_key = json.dumps([norm, detected_target], ensure_ascii=False, separators=(',', ':'))
            tooltip_rows = build_kwd_tooltip_data(norm)
            evidence = next((record for record in info.get('match_records', []) if record[0] == norm), None)
            if evidence:
                _, matched_record, matched_text = evidence
                mode = config.mode if config else 'exact'
                registered_term = str(matched_record.term).strip()
                common = SequenceMatcher(None, matched_text, registered_term, autojunk=False).find_longest_match(
                    0, len(matched_text), 0, len(registered_term))
                matched_core = matched_text[common.a:common.a + common.size] if common.size >= 2 else ''
                registered_core = registered_term[common.b:common.b + common.size] if common.size >= 2 else ''
                if mode == 'similar':
                    saved = (approved_partials or {}).get(str(matched_record.kwd_no or ''), {})
                    approved = saved.get('expressions', []) if saved.get('term') == registered_term else []
                    approved_hit = next((expr for expr in approved if str(expr).casefold() in matched_text.casefold()), None)
                    condition = (f"2글자 이상 승인 표현 ‘{approved_hit}’가 입력 문구의 단어 경계와 일치했습니다."
                                 if approved_hit else "2글자 이상인 입력·등록 내용어 토큰을 Kiwi로 분석해 일치했습니다.")
                elif mode == 'partial':
                    minimum = max(2, int(config.partial_min_len if config else 2))
                    condition = f"글자 수 매칭 방식에서 최소 {minimum}글자 조건을 충족한 부분 문자열이 일치했습니다."
                else:
                    condition = "키워드 완전 일치 방식으로 등록 표현이 입력 문구에서 발견됐습니다. 설정한 표기 비교 옵션이 적용될 수 있습니다."
                evidence_rows = [
                    ('매칭 결과', matched_text, registered_term, matched_core, registered_core),
                    ('매칭 조건', condition),
                ]
                date_row = next((idx for idx, row in enumerate(tooltip_rows) if row and row[0] == LAST_SEARCH_LABEL), None)
                insert_at = date_row + 1 if date_row is not None else len(tooltip_rows)
                if insert_at < len(tooltip_rows) and tooltip_rows[insert_at][0] == "키워드 등록일자":
                    insert_at += 1
                tooltip_rows[insert_at:insert_at] = evidence_rows
            HIGHLIGHT_TOOLTIP_MAP[tooltip_key] = tooltip_rows

            frag_content = (
                f"<span class='kwdno-entry' data-kwd-toggle='{html.escape(toggle_key, quote=True)}'>"
                f"<span class='kwdno-link' data-kwd='{html.escape(norm, quote=True)}' "
                f"data-group-key='{html.escape(detected_target, quote=True)}' "
                f"data-tooltip-key='{html.escape(tooltip_key, quote=True)}' "
                f"data-copy-label='{html.escape(norm, quote=True)}' "
                f"style='color:{color}; text-decoration:underline; cursor:pointer'>"
                f"<b>{html.escape(token or norm)}</b></span></span>"
            )
            frag_parts.append(frag_content)

        ids_html = f"<span class='kwdno-group'>{''.join(frag_parts)}</span>" if frag_parts else ""

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
        decorated = (f"{html.escape(leading_ws)}<span class='{cls}' tabindex='0' "
                     f"aria-label='검출 키워드 표시 전환'>{inner_html}</span>{html.escape(trailing_ws)}")
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
st.set_page_config(page_title=f"Keyword Risk Analyzer · {APP_VERSION}", layout="wide")

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
/* Override the main content's large default top inset. */
section.main > div.block-container,
div[data-testid="stMainBlockContainer"],
.main .block-container {
    padding-top: 0.75rem !important;
}
/* Make the main tab navigation easier to scan. */
div[data-testid="stTabs"] [role="tab"],
.st-key-main_app_tabs [role="tab"] {
    font-size: 1.25rem !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)
st.title("🔎 광고심의 자동화 솔루션")

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

def _password_reset_redirect_url():
    configured_url = os.getenv('APP_PUBLIC_URL', '').strip()
    current_url = configured_url or st.context.url
    parsed = urlsplit(current_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('?? ?? URL? ??? ? ????.')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', '', ''))


def _read_password_recovery_hash(clear_url=False):
    if clear_url:
        st.session_state.pop(_RECOVERY_COMPONENT_KEY, None)
    component_state = st.session_state.get(_RECOVERY_COMPONENT_KEY, {})
    result = _RECOVERY_COMPONENT(
        key=_RECOVERY_COMPONENT_KEY,
        data={'known_hash': component_state.get('hash', ''), 'clear_url': clear_url},
        on_hash_change=lambda: None,
    )
    return (st.session_state.get(_RECOVERY_COMPONENT_KEY, {}).get('hash')
            or getattr(result, 'hash', None) or '')


def render_cloud_login():
    """Authenticate before reading shared data; validate roles on every rerun."""
    repository = SupabaseRepository()
    clear_url = st.session_state.pop('_clear_recovery_url', False)
    recovery_hash = _read_password_recovery_hash(clear_url=clear_url)
    reset_completed = st.session_state.pop('_password_reset_done', False)
    signup_completed = st.session_state.pop('_signup_completed', False)

    if recovery_hash:
        recovery = parse_qs(recovery_hash.lstrip('#'))
        if recovery.get('type', [''])[0] == 'recovery':
            access_token = recovery.get('access_token', [''])[0]
            if access_token:
                st.subheader('새 비밀번호 설정')
                st.caption('복구 링크가 확인되었습니다. 새 비밀번호를 입력하세요.')
                with st.form('cloud_password_update'):
                    new_password = st.text_input('새 비밀번호', type='password')
                    confirm_password = st.text_input('새 비밀번호 확인', type='password')
                    submit = st.form_submit_button('비밀번호 변경')
                if submit:
                    if not new_password:
                        st.error('새 비밀번호를 입력하세요.')
                    elif new_password != confirm_password:
                        st.error('두 비밀번호가 서로 다릅니다.')
                    else:
                        try:
                            repository.update_password(access_token, new_password)
                            st.session_state['_clear_recovery_url'] = True
                            st.session_state['_password_reset_done'] = True
                            st.rerun()
                        except (StorageError, PermissionError):
                            st.error('비밀번호를 변경하지 못했습니다. 복구 링크가 만료되었거나 비밀번호 정책을 확인해야 합니다.')
            else:
                st.error('복구 링크가 만료되었거나 이미 사용되었습니다. 비밀번호 찾기를 다시 요청하세요.')
            st.stop()

    session = st.session_state.get('auth_session')
    storage_action = st.session_state.pop('_auth_persistence_action', None)
    component_state = st.session_state.get(_AUTH_SESSION_COMPONENT_KEY, {})
    if storage_action == 'clear':
        auth_storage_mode = 'clear'
    elif session and session.get('refresh_token'):
        auth_storage_mode = 'save'
    else:
        auth_storage_mode = 'read'
    _AUTH_SESSION_COMPONENT(
        key=_AUTH_SESSION_COMPONENT_KEY,
        data={
            'action': auth_storage_mode,
            'refresh_token': (session or {}).get('refresh_token', ''),
            'known_refresh_token': component_state.get('refresh_token', ''),
            'checked': bool(component_state.get('checked')),
        },
    )
    if component_state.get('storage_error'):
        st.sidebar.warning('브라우저가 로그인 유지를 허용하지 않습니다. 새로고침 후 다시 로그인해야 합니다.')

    if not session and auth_storage_mode != 'clear':
        if not component_state.get('checked'):
            st.info('로그인 상태를 확인하고 있습니다…')
            st.stop()
        persisted_refresh_token = component_state.get('refresh_token', '')
        if persisted_refresh_token:
            try:
                session = repository.refresh(persisted_refresh_token)
            except StorageError as exc:
                if 'connection failed' in str(exc).lower():
                    st.error('로그인 상태를 확인하기 위해 Supabase에 연결할 수 없습니다.')
                    if st.button('다시 시도', key='cloud_auth_restore_retry'):
                        st.rerun()
                    st.stop()
                st.session_state['_auth_persistence_action'] = 'clear'
                st.rerun()
            if not session.get('expires_at'):
                session['expires_at'] = time.time() + int(session.get('expires_in') or 3600)
            st.session_state.auth_session = session
            st.session_state['_auth_persistence_action'] = 'save'
            st.rerun()

    if st.sidebar.button('로그아웃', key='cloud_logout'):
        if st.session_state.get('unmatched_pending_collections'):
            st.error('아직 저장하지 못한 미매칭 후보가 있습니다. 수집 저장 재시도 후 로그아웃하세요.')
            st.stop()
        session = st.session_state.get('auth_session')
        try:
            if session:
                repository.logout(session['access_token'])
        finally:
            st.session_state.clear()
            st.session_state['_auth_persistence_action'] = 'clear'
        st.rerun()

    session = st.session_state.get('auth_session')
    if not session:
        _, login_col, _ = st.columns([1, 2, 1])
        with login_col:
            st.subheader('사내 계정 로그인')
            if reset_completed:
                st.success('비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.')
            if signup_completed:
                st.success('\uac00\uc785 \uc694\uccad\uc744 \ucc98\ub9ac\ud588\uc2b5\ub2c8\ub2e4. \uc774\uba54\uc77c \ud655\uc778 \ud6c4 \uad00\ub9ac\uc790\uc5d0\uac8c \uc0ac\uc6a9 \uc2b9\uc778\uc744 \uc694\uccad\ud558\uc138\uc694. \uc2b9\uc778 \uc804\uae4c\uc9c0\ub294 \uc571\uc5d0 \uc811\uadfc\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.')
            auth_view = st.session_state.get('auth_view', 'login')
            if auth_view == 'signup':
                with st.form('cloud_signup_form'):
                    signup_email = st.text_input('\uc774\uba54\uc77c', key='cloud_signup_email')
                    signup_password = st.text_input('\ube44\ubc00\ubc88\ud638', type='password', key='cloud_signup_password')
                    signup_password_confirm = st.text_input('\ube44\ubc00\ubc88\ud638 \ud655\uc778', type='password', key='cloud_signup_password_confirm')
                    signup_submit = st.form_submit_button('\ud68c\uc6d0\uac00\uc785', key='cloud_signup_submit')
                if signup_submit:
                    if not signup_email.strip() or not signup_password:
                        st.error('\uc774\uba54\uc77c\uacfc \ube44\ubc00\ubc88\ud638\ub97c \ubaa8\ub450 \uc785\ub825\ud558\uc138\uc694.')
                    elif signup_password != signup_password_confirm:
                        st.error('\ube44\ubc00\ubc88\ud638\uac00 \uc11c\ub85c \ub2e4\ub985\ub2c8\ub2e4.')
                    else:
                        redirect_url = ''
                        try:
                            redirect_url = _password_reset_redirect_url()
                            repository.sign_up(signup_email, signup_password, redirect_url)
                            st.session_state['auth_view'] = 'login'
                            st.session_state['_signup_completed'] = True
                            st.rerun()
                        except StorageError as exc:
                            st.error('\ud68c\uc6d0\uac00\uc785 \uc694\uccad\uc744 \ucc98\ub9ac\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.')
                            st.caption(f'Supabase response: {exc}')
                            if '(400)' in str(exc):
                                st.caption('\uac00\uc785 \ud5c8\uc6a9, Redirect URLs, \uc774\uba54\uc77c \ud655\uc778 \ubc0f \ube44\ubc00\ubc88\ud638 \uc815\ucc45\uc744 \ud655\uc778\ud558\uc138\uc694.')
                            elif '(429)' in str(exc):
                                st.caption('\uac00\uc785 \uc694\uccad \ud55c\ub3c4\uc5d0 \uac78\ub838\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud558\uc138\uc694.')
                            elif '(500)' in str(exc):
                                st.caption('Supabase Auth\uc758 \ud655\uc778 \uc774\uba54\uc77c \ubc1c\uc1a1(SMTP) \uc124\uc815\uc744 \ud655\uc778\ud558\uc138\uc694.')
                            if redirect_url:
                                st.code(redirect_url)
                        except ValueError as exc:
                            st.error('\ud68c\uc6d0\uac00\uc785 \uc694\uccad\uc744 \ucc98\ub9ac\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.')
                            st.caption(str(exc))
                if st.button('\ub85c\uadf8\uc778 \ud654\uba74\uc73c\ub85c \ub3cc\uc544\uac00\uae30', key='cloud_signup_back'):
                    st.session_state.auth_view = 'login'
                    st.rerun()
            elif st.session_state.get('auth_view') == 'password_reset_request':
                with st.form('cloud_password_reset_request'):
                    email = st.text_input('계정 이메일')
                    submit = st.form_submit_button('복구 이메일 보내기')
                if submit:
                    if not email.strip():
                        st.error('\uacc4\uc815 \uc774\uba54\uc77c\uc744 \uc785\ub825\ud558\uc138\uc694.')
                    else:
                        redirect_url = ''
                        try:
                            redirect_url = _password_reset_redirect_url()
                            repository.request_password_reset(email, redirect_url)
                            st.info('\ud574\ub2f9 \uc774\uba54\uc77c\uc758 \uacc4\uc815\uc774 \uc788\uc73c\uba74 \ube44\ubc00\ubc88\ud638 \ubcf5\uad6c \ub9c1\ud06c\ub97c \ubcf4\ub0c8\uc2b5\ub2c8\ub2e4.')
                        except StorageError as exc:
                            st.error('\ubcf5\uad6c \uc774\uba54\uc77c \uc694\uccad\uc744 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.')
                            st.caption(f'Supabase response: {exc}')
                            if '(400)' in str(exc):
                                st.caption('HTTP 400: Redirect URLs \ud56d\ubaa9\uacfc \uc544\ub798 \uc774\ub3d9 \uc8fc\uc18c\uac00 \uc77c\uce58\ud558\ub294\uc9c0 \ud655\uc778\ud558\uc138\uc694.')
                            elif '(429)' in str(exc):
                                st.caption('HTTP 429: \uc694\uccad \ud55c\ub3c4\uc5d0 \uac78\ub838\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud558\uc138\uc694.')
                            elif '(500)' in str(exc):
                                st.caption('HTTP 500: Auth \uc774\uba54\uc77c \ubc1c\uc1a1(SMTP) \uc124\uc815\uacfc \uc774\uba54\uc77c \ud15c\ud50c\ub9bf\uc744 \ud655\uc778\ud558\uc138\uc694.')
                            if redirect_url:
                                st.code(redirect_url)
                        except (PermissionError, ValueError) as exc:
                            st.error('\ubcf5\uad6c \uc774\uba54\uc77c \uc694\uccad\uc744 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4.')
                            st.caption(str(exc))
                if st.button('로그인 화면으로 돌아가기', key='cloud_reset_back'):
                    st.session_state.auth_view = 'login'
                    st.rerun()
            else:
                with st.form('cloud_login'):
                    email = st.text_input('이메일')
                    password = st.text_input('비밀번호', type='password')
                    submit = st.form_submit_button('로그인')
                if submit:
                    try:
                        session = repository.login(email, password)
                        if not session.get('expires_at'):
                            session['expires_at'] = time.time() + int(session.get('expires_in') or 3600)
                        st.session_state.auth_session = session
                        st.session_state['_auth_persistence_action'] = 'save'
                        st.session_state.pop('auth_view', None)
                        st.rerun()
                    except (StorageError, PermissionError) as exc:
                        st.error('로그인에 실패했습니다. 계정과 비밀번호를 확인하세요.')
                        st.caption(f'Supabase response: {exc}')
                if st.button('비밀번호를 잊으셨나요?', key='cloud_forgot_password'):
                    st.session_state.auth_view = 'password_reset_request'
                    st.rerun()
                if st.button('\ud68c\uc6d0\uac00\uc785', key='cloud_signup_open'):
                    st.session_state.auth_view = 'signup'
                    st.rerun()
            st.stop()
    try:
        if session.get('expires_at', 0) < time.time() + 300:
            session = repository.refresh(session['refresh_token'])
            if not session.get('expires_at'):
                session['expires_at'] = time.time() + int(session.get('expires_in') or 3600)
            st.session_state.auth_session = session
            st.session_state['_auth_persistence_action'] = 'save'
            st.rerun()
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


KEYWORD_REQUEST_TYPE_LABELS = {
    'risk_grade_adjustment': '리스크 등급 조정요청',
    'review_criteria_change': '심의기준 변경요청',
    'new_keyword_registration': '신규키워드 등록요청',
}


def render_keyword_request_form():
    """Render the authenticated Supabase-only request form in the sidebar."""
    if not cloud_enabled():
        return
    keyword_options = {}
    keywords = st.session_state.get('kw_df')
    if keywords is not None and {'kwd_no', '키워드명'}.issubset(keywords.columns):
        keyword_rows = keywords[['kwd_no', '키워드명']].fillna('').astype(str)
        keyword_rows = keyword_rows.sort_values(
            ['kwd_no', '키워드명'], key=lambda values: values.str.casefold(), kind='mergesort'
        )
        for _, row in keyword_rows.iterrows():
            keyword_code = row['kwd_no'].strip().upper()
            keyword_name = row['키워드명'].strip()
            if keyword_code:
                keyword_options[f'{keyword_code} | {keyword_name}'] = keyword_code

    with st.sidebar.expander('키워드 문의', expanded=False):
        request_type = st.selectbox(
            '문의 유형',
            options=sorted(KEYWORD_REQUEST_TYPE_LABELS,
                           key=lambda value: KEYWORD_REQUEST_TYPE_LABELS[value]),
            format_func=lambda value: KEYWORD_REQUEST_TYPE_LABELS[value],
            key='keyword_request_type',
        )
        is_new_keyword_request = request_type == 'new_keyword_registration'
        if is_new_keyword_request:
            st.caption('신규키워드는 한 항목씩 입력해 주세요. 여러 키워드는 쉼표(,)로 구분하세요. 예: 키워드A, 키워드B')
        with st.form('keyword_request_form', clear_on_submit=True):
            selected_keyword = st.selectbox(
                '키워드 검색 (kwd_no / 키워드명)',
                options=list(keyword_options),
                index=None,
                placeholder='번호 또는 키워드명을 입력하세요.',
                filter_mode='contains',
                disabled=not keyword_options,
                key='keyword_request_kwd_select',
            )
            detail = st.text_area(
                '요청 상세 내용' if is_new_keyword_request else '요청 상세 내용 (선택)', max_chars=4000,
                key='keyword_request_detail',
                placeholder='키워드A, 키워드B' if is_new_keyword_request else '',
                help=('신규키워드는 쉼표(,)로 구분해 입력하세요.' if is_new_keyword_request
                      else '변경이 필요한 이유나 원하는 내용을 적어주세요. 최대 4,000자까지 입력할 수 있습니다.'),
            )
            submitted = st.form_submit_button('입력', type='primary')

        if not submitted:
            return
        if is_new_keyword_request:
            terms, seen = [], set()
            for value in detail.split(','):
                term = value.strip()
                term_norm = unicodedata.normalize('NFKC', term).casefold().strip()
                if term and term_norm not in seen:
                    terms.append(term)
                    seen.add(term_norm)
            if not terms:
                st.error('등록 요청할 키워드를 쉼표로 구분해 입력하세요.')
                return
            try:
                queued = SupabaseRepository().submit_new_keyword_registration_requests(
                    terms, st.session_state.auth_session['access_token']
                )
            except (StorageError, PermissionError, KeyError, ValueError) as exc:
                st.error('신규 키워드 등록 요청을 접수하지 못했습니다. Supabase 연결과 입력을 확인하세요.')
                st.caption(str(exc))
                return
            st.success(f'신규 키워드 {int(queued or 0)}건을 미매칭 표현 목록에 요청 상태로 추가했습니다.')
            return
        keyword_code = keyword_options.get(selected_keyword, '')
        if not keyword_code:
            st.error('\ubaa9\ub85d\uc5d0\uc11c \ud0a4\uc6cc\ub4dc \ubc88\ud638 \ub610\ub294 \ud0a4\uc6cc\ub4dc\uba85\uc744 \uac80\uc0c9\ud574 \uc120\ud0dd\ud558\uc138\uc694.')
            return

        repository = SupabaseRepository()
        try:
            if keyword_code:
                latest_keywords = repository.load_keywords()
                rows_by_code = {
                    str(row['kwd_no']).strip().upper(): row
                    for _, row in latest_keywords.iterrows()
                }
                keyword_row = rows_by_code.get(keyword_code)
                if keyword_row is None:
                    st.error('\ud604\uc7ac \uacf5\uc720 DB\uc5d0\uc11c kwd_no\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \ucd5c\uc2e0 \ubc88\ud638\ub97c \ud655\uc778\ud558\uc138\uc694.')
                    return
                request_kwd_no = str(keyword_row['kwd_no']).strip()
                request_keyword_name = selected_keyword.split(' | ', 1)[1].strip() if ' | ' in selected_keyword else selected_keyword
            else:
                request_kwd_no = ''
                request_keyword_name = '\uc2e0\uaddc \ud0a4\uc6cc\ub4dc'

            user = st.session_state.cloud_user
            access_token = st.session_state.auth_session['access_token']
            request_row = repository.submit_keyword_request(
                {
                    'requester_id': user['id'],
                    'requester_email': user.get('email', ''),
                    'kwd_no': request_kwd_no,
                    'keyword_name': request_keyword_name,
                    'request_type': request_type,
                    'request_detail': detail.strip(),
                },
                access_token,
            )
        except (StorageError, PermissionError, KeyError, ValueError) as exc:
            st.error('문의 등록을 완료하지 못했습니다. Supabase 설정과 접근 권한을 확인하세요.')
            st.caption(str(exc))
            return

        st.success('문의가 등록되었습니다. 키워드 문의 내역 탭에서 확인할 수 있습니다.')
        try:
            if repository.load_request_email_notifications():
                send_keyword_request_email(request_row)
        except (NotificationConfigurationError, NotificationDeliveryError, StorageError) as exc:
            st.warning('문의는 등록됐지만 관리자 이메일 알림은 발송되지 않았습니다.')
            st.caption(str(exc))

if cloud_enabled():
    st.sidebar.caption('Supabase 공유 저장소')
    if st.sidebar.button('최신 데이터 불러오기'):
        st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
        load_hits_log.clear()
    render_keyword_request_form()
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


KEYWORD_REQUEST_STATUSES = ('대기', '검토중', '처리완료')


def format_keyword_request_time(value):
    parsed = pd.to_datetime(value, utc=True, errors='coerce')
    if pd.isna(parsed):
        return str(value or '')
    return parsed.tz_convert('Asia/Seoul').strftime('%Y-%m-%d %H:%M')


@st.dialog('문의 상세 및 처리', width='large')
def render_keyword_request_dialog(row, access_token):
    request_id = str(row.get('id', '')).strip()
    receipt_no = f"KR-{request_id[:8].upper()}"
    current_user = st.session_state.get('cloud_user') or {}
    current_user_id = str(current_user.get('id', ''))
    current_user_email = str(current_user.get('email', ''))
    admin_mode = is_admin()
    owner_mode = bool(current_user_id and current_user_id == str(row.get('requester_id', '')))
    st.write(f"**접수번호:** {receipt_no}")
    st.write(f"**키워드no.:** {row.get('kwd_no', '')}")
    st.write(f"**키워드명:** {row.get('keyword_name', '')}")
    st.caption(f"접수 시각: {format_keyword_request_time(row.get('created_at', ''))}")
    st.write(f"**문의 유형:** {KEYWORD_REQUEST_TYPE_LABELS.get(row.get('request_type'), row.get('request_type', ''))}")
    st.write(f"**요청자 이메일:** {row.get('requester_email', '')}")

    repository = SupabaseRepository()
    st.markdown('#### 문의 및 답변 내역')
    legacy_reply = str(row.get('admin_reply') or '').strip()
    messages_loaded = True
    try:
        messages = repository.load_keyword_request_messages(request_id, access_token)
    except (StorageError, PermissionError) as exc:
        messages = []
        messages_loaded = False
        st.warning('대화 내역 기능을 사용하려면 키워드 문의 댓글용 DB 설정을 적용해야 합니다.')
        st.caption(str(exc))
    children_by_parent = {
        str(message['reply_to_id']): message
        for message in messages
        if message.get('reply_to_id')
    }
    user_inquiries = [
        message for message in messages
        if message.get('author_role') == 'user' and not message.get('reply_to_id')
    ]
    inquiry_number_by_message = {}
    entry_code_by_message = {}
    for inquiry_number, root_inquiry in enumerate(user_inquiries, start=1):
        current = root_inquiry
        root_code = f'Q{inquiry_number:02d}'
        visited_ids = set()
        admin_answer_number = 0
        user_followup_number = 0
        while current:
            current_id = str(current.get('id', ''))
            if not current_id or current_id in visited_ids:
                break
            visited_ids.add(current_id)
            inquiry_number_by_message[current_id] = inquiry_number
            if current is root_inquiry:
                entry_code_by_message[current_id] = root_code
            current = children_by_parent.get(current_id)
            if current:
                current_id = str(current.get('id', ''))
                if current.get('author_role') == 'admin':
                    admin_answer_number += 1
                    entry_code_by_message[current_id] = f'{root_code}_A{admin_answer_number}'
                else:
                    user_followup_number += 1
                    entry_code_by_message[current_id] = f'{root_code}-R{user_followup_number}'

    pending_inquiry_ids = {
        str(message.get('id', '')) for message in messages
        if message.get('author_role') == 'user'
        and str(message.get('id', '')) not in children_by_parent
    }
    feedback_target_key = f'keyword_request_feedback_target_{request_id}'
    followup_target_key = f'keyword_request_followup_target_{request_id}'
    selected_followup_target = st.session_state.get(followup_target_key)
    if selected_followup_target and selected_followup_target in children_by_parent:
        st.session_state.pop(followup_target_key, None)
        selected_followup_target = None
    selected_feedback_target = st.session_state.get(feedback_target_key)
    if selected_feedback_target and selected_feedback_target not in pending_inquiry_ids:
        st.session_state.pop(feedback_target_key, None)
        selected_feedback_target = None

    def render_owner_inquiry_controls(inquiry, entry_code):
        inquiry_id = str(inquiry.get('id', ''))
        if not (messages_loaded and owner_mode and inquiry.get('author_role') == 'user'
                and str(inquiry.get('author_id', '')) == current_user_id):
            return
        with st.expander(f'{entry_code} 수정'):
            with st.form(f'keyword_inquiry_edit_form_{inquiry_id}'):
                edited_type = None
                if inquiry.get('is_initial'):
                    request_types = list(KEYWORD_REQUEST_TYPE_LABELS)
                    edited_type = st.selectbox(
                        '문의 유형', request_types,
                        index=request_types.index(row['request_type']),
                        format_func=KEYWORD_REQUEST_TYPE_LABELS.get,
                        key=f'keyword_inquiry_edit_type_{inquiry_id}',
                    )
                edited_body = st.text_area(
                    '문의 내용', value=inquiry.get('body', ''), max_chars=4000,
                    key=f'keyword_inquiry_edit_body_{inquiry_id}',
                )
                save_inquiry = st.form_submit_button(f'{entry_code} 수정 저장', type='primary')
            if save_inquiry:
                if not inquiry.get('is_initial') and not edited_body.strip():
                    st.error('문의 내용을 입력하세요.')
                    return
                if edited_type and not row.get('kwd_no') and edited_type != 'new_keyword_registration':
                    st.error('키워드가 지정되지 않은 요청은 신규키워드 등록요청으로 저장하세요.')
                    return
                try:
                    repository.mutate_own_keyword_inquiry(
                        request_id, inquiry_id, 'edit', access_token,
                        body=edited_body, request_type=edited_type,
                    )
                    st.session_state['keyword_request_owner_edit_saved'] = True
                    st.rerun()
                except (StorageError, PermissionError, ValueError) as exc:
                    st.error(f'{entry_code} 문의를 수정하지 못했습니다.')
                    st.caption(str(exc))

        confirm_key = f'keyword_inquiry_delete_confirm_{inquiry_id}'
        if st.button(f'{entry_code} 삭제', key=f'keyword_inquiry_delete_{inquiry_id}'):
            st.session_state[confirm_key] = True
        if st.session_state.get(confirm_key):
            st.warning(f'{entry_code} 문의와 연결된 답변·재문의를 함께 영구 삭제합니다. 다른 문의는 유지됩니다.')
            cancel_col, delete_col = st.columns(2)
            if cancel_col.button('취소', key=f'keyword_inquiry_delete_cancel_{inquiry_id}'):
                st.session_state.pop(confirm_key, None)
                st.rerun()
            if delete_col.button(
                f'{entry_code} 영구 삭제 확인', type='primary',
                key=f'keyword_inquiry_delete_submit_{inquiry_id}',
            ):
                try:
                    repository.mutate_own_keyword_inquiry(
                        request_id, inquiry_id, 'delete', access_token,
                    )
                    st.session_state.pop(confirm_key, None)
                    st.session_state['keyword_inquiry_delete_saved'] = True
                    st.rerun()
                except (StorageError, PermissionError, ValueError) as exc:
                    st.error(f'{entry_code} 문의를 삭제하지 못했습니다.')
                    st.caption(str(exc))

    def render_admin_feedback_controls(inquiry, entry_code):
        inquiry_id = str(inquiry.get('id', ''))
        if not (messages_loaded and admin_mode and inquiry_id in pending_inquiry_ids):
            return
        if selected_feedback_target != inquiry_id:
            if st.button(
                f'{entry_code} \ud53c\ub4dc\ubc31 \uc791\uc131',
                key=f'keyword_request_feedback_open_{request_id}_{inquiry_id}',
            ):
                st.session_state[feedback_target_key] = inquiry_id
                st.rerun()
            return

        current_status = inquiry.get('status') or '\ub300\uae30'
        if current_status not in KEYWORD_REQUEST_STATUSES:
            current_status = '\ub300\uae30'
        st.caption(f'{entry_code} \ud53c\ub4dc\ubc31\uacfc \ucc98\ub9ac\uc0c1\ud0dc\ub97c \ud568\uaed8 \uc800\uc7a5\ud569\ub2c8\ub2e4.')
        with st.form(f'keyword_request_feedback_form_{request_id}_{inquiry_id}'):
            feedback_body = st.text_area(
                '\uad00\ub9ac\uc790 \ud53c\ub4dc\ubc31', max_chars=4000,
                key=f'keyword_request_feedback_body_{request_id}_{inquiry_id}',
            )
            feedback_status = st.selectbox(
                '\ucc98\ub9ac\uc0c1\ud0dc', KEYWORD_REQUEST_STATUSES,
                index=KEYWORD_REQUEST_STATUSES.index(current_status),
                key=f'keyword_request_feedback_status_{request_id}_{inquiry_id}',
            )
            submit_feedback = st.form_submit_button('\ud53c\ub4dc\ubc31 \ubc0f \ucc98\ub9ac\uc0c1\ud0dc \uc800\uc7a5', type='primary')
        if submit_feedback:
            if not feedback_body.strip():
                st.error('\ud53c\ub4dc\ubc31 \ub0b4\uc6a9\uc744 \uc785\ub825\ud558\uc138\uc694.')
            else:
                try:
                    repository.respond_to_keyword_inquiry(
                        request_id, inquiry_id, feedback_body, feedback_status, access_token,
                    )
                    st.session_state['keyword_request_message_saved'] = True
                    st.rerun()
                except (StorageError, PermissionError, ValueError) as exc:
                    st.error('\ud53c\ub4dc\ubc31\uacfc \ucc98\ub9ac\uc0c1\ud0dc\ub97c \uc800\uc7a5\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.')
                    st.caption(str(exc))

    for inquiry_number, root_inquiry in enumerate(user_inquiries, start=1):
        root_id = str(root_inquiry.get('id', ''))
        root_code = f'Q{inquiry_number:02d}'
        with st.container(border=True):
            root_status = root_inquiry.get('status') or '\ub300\uae30'
            st.caption(
                f"{root_code} | \uc0ac\uc6a9\uc790 \ubb38\uc758 | \ucc98\ub9ac\uc0c1\ud0dc: {root_status} | "
                f"{root_inquiry.get('author_email', '')} | "
                f"{format_keyword_request_time(root_inquiry.get('created_at', ''))}"
            )
            st.write(root_inquiry.get('body', ''))
            render_owner_inquiry_controls(root_inquiry, root_code)
            render_admin_feedback_controls(root_inquiry, root_code)
            current = root_inquiry
            visited_ids = {root_id}
            admin_answer_number = 0
            user_followup_number = 0
            while current:
                current_id = str(current.get('id', ''))
                reply = children_by_parent.get(current_id)
                if not reply:
                    if (
                        current.get('is_initial') and legacy_reply
                        and current_id not in children_by_parent
                    ):
                        st.divider()
                        st.caption(f'{root_code}_A1 | \uae30\uc874 \uad00\ub9ac\uc790 \ub2f5\ubcc0 | \uc791\uc131 \uc2dc\uac01 \uae30\ub85d \uc5c6\uc74c')
                        st.write(legacy_reply)
                    break

                reply_id = str(reply.get('id', ''))
                if not reply_id or reply_id in visited_ids:
                    break
                visited_ids.add(reply_id)
                reply_role = reply.get('author_role')
                if reply_role == 'admin':
                    admin_answer_number += 1
                    entry_code = f'{root_code}_A{admin_answer_number}'
                    entry_title = '\uae30\uc874 \uad00\ub9ac\uc790 \ub2f5\ubcc0' if reply.get('is_legacy') else '\uad00\ub9ac\uc790 \ub2f5\ubcc0'
                else:
                    user_followup_number += 1
                    entry_code = f'{root_code}-R{user_followup_number}'
                    entry_title = '\uc0ac\uc6a9\uc790 \uc7ac\ubb38\uc758'

                st.divider()
                reply_status = reply.get('status') or '\ub300\uae30'
                status_label = f' | \ucc98\ub9ac\uc0c1\ud0dc: {reply_status}' if reply_role == 'user' else ''
                if reply.get('is_legacy'):
                    st.caption(f"{entry_code} | {entry_title}{status_label} | \uc791\uc131 \uc2dc\uac01 \uae30\ub85d \uc5c6\uc74c")
                else:
                    st.caption(
                        f"{entry_code} | {entry_title}{status_label} | {reply.get('author_email', '')} | "
                        f"{format_keyword_request_time(reply.get('created_at', ''))}"
                    )
                st.write(reply.get('body', ''))
                if reply_role == 'user':
                    render_owner_inquiry_controls(reply, entry_code)
                    render_admin_feedback_controls(reply, entry_code)

                if (
                    messages_loaded and not admin_mode and reply_role == 'admin'
                    and reply_id not in children_by_parent
                ):
                    if selected_followup_target == reply_id:
                        with st.form(f'keyword_request_followup_form_{request_id}_{reply_id}'):
                            followup_body = st.text_area(
                                '\uc7ac\ubb38\uc758 \ub0b4\uc6a9', max_chars=4000,
                                key=f'keyword_request_followup_body_{request_id}_{reply_id}',
                            )
                            submit_followup = st.form_submit_button('\uc7ac\ubb38\uc758 \ub4f1\ub85d')
                        if submit_followup:
                            if not followup_body.strip():
                                st.error('\uc7ac\ubb38\uc758 \ub0b4\uc6a9\uc744 \uc785\ub825\ud558\uc138\uc694.')
                            else:
                                try:
                                    repository.add_keyword_request_message(
                                        request_id, current_user_id, current_user_email,
                                        followup_body, access_token, author_role='user',
                                        reply_to_id=reply_id,
                                    )
                                    st.session_state.pop(followup_target_key, None)
                                    st.session_state['keyword_request_message_saved'] = True
                                    st.rerun()
                                except (StorageError, PermissionError, ValueError) as exc:
                                    st.error('\uc7ac\ubb38\uc758\ub97c \uc800\uc7a5\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.')
                                    st.caption(str(exc))
                    elif st.button(
                        '\uc774 \ub2f5\ubcc0\uc5d0 \uc7ac\ubb38\uc758',
                        key=f'keyword_request_followup_open_{request_id}_{reply_id}',
                    ):
                        st.session_state[followup_target_key] = reply_id
                        st.rerun()

                current = reply

    if messages_loaded and not admin_mode and current_user_id and current_user_email:
        with st.form(f'keyword_request_new_message_form_{request_id}'):
            new_message = st.text_area(
                '\uc0c8 \ubb38\uc758 \ub4f1\ub85d',
                max_chars=4000, key=f'keyword_request_message_body_{request_id}',
            )
            submit_message = st.form_submit_button('\uc0c8 \ubb38\uc758 \uc81c\ucd9c', type='primary')
        if submit_message:
            try:
                repository.add_keyword_request_message(
                    request_id, current_user_id, current_user_email,
                    new_message, access_token,
                )
                st.session_state['keyword_request_message_saved'] = True
                st.rerun()
            except (StorageError, PermissionError, ValueError) as exc:
                st.error('\uc0c8 \ubb38\uc758\ub97c \uc800\uc7a5\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.')
                st.caption(str(exc))

    orphaned_replies = [
        message for message in messages
        if message.get('author_role') == 'admin' and not message.get('reply_to_id')
    ]
    for message in orphaned_replies:
        with st.container(border=True):
            st.caption(
                f"기존 관리자 답변 · {message.get('author_email', '')} · "
                f"{format_keyword_request_time(message.get('created_at', ''))}"
            )
            st.write(message.get('body', ''))

    if admin_mode or owner_mode:
        confirm_key = f'keyword_request_delete_confirm_{request_id}'
        if st.button('접수건 전체 삭제', key=f'keyword_request_delete_{request_id}'):
            st.session_state[confirm_key] = True

        if st.session_state.get(confirm_key):
            st.warning('이 접수건과 모든 문의·답변을 영구 삭제할까요? 삭제한 내역은 복구할 수 없습니다.')
            cancel_col, delete_col = st.columns(2)
            with cancel_col:
                cancel_delete = st.button('취소', key=f'keyword_request_cancel_delete_{request_id}')
            with delete_col:
                confirm_delete = st.button(
                    '영구 삭제 확인', type='primary', key=f'keyword_request_confirm_delete_{request_id}',
                )
            if cancel_delete:
                st.session_state.pop(confirm_key, None)
                st.rerun()
            if confirm_delete:
                try:
                    repository.delete_keyword_request(request_id, access_token)
                    st.session_state.pop(confirm_key, None)
                    st.session_state['keyword_request_delete_saved'] = True
                    st.session_state['keyword_request_history_epoch'] = st.session_state.get('keyword_request_history_epoch', 0) + 1
                    st.rerun()
                except (StorageError, PermissionError, ValueError) as exc:
                    st.error('문의를 삭제하지 못했습니다. 본인 문의 또는 관리자 권한을 확인하세요.')
                    st.caption(str(exc))


def render_keyword_requests_tab():
    repository = SupabaseRepository()
    access_token = st.session_state.auth_session['access_token']

    if st.session_state.pop('keyword_request_owner_edit_saved', False):
        st.success('문의 내용을 수정했습니다.')
    if st.session_state.pop('keyword_inquiry_delete_saved', False):
        st.success('선택한 문의와 연결된 답변·재문의를 삭제했습니다.')
    if st.session_state.pop('keyword_request_update_saved', False):
        st.success('문의 처리 상태와 관리자 답변을 저장했습니다.')
    if st.session_state.pop('keyword_request_delete_saved', False):
        st.success('문의를 삭제했습니다.')
    if st.session_state.pop('keyword_request_message_saved', False):
        st.success('대화 내역에 메시지를 추가했습니다.')

    if is_admin():
        setting_key = 'request_email_notifications_enabled'
        try:
            if setting_key not in st.session_state:
                st.session_state[setting_key] = repository.load_request_email_notifications(access_token)
            configured = is_notification_configured()
            if not configured:
                st.warning(
                    '이메일 알림을 사용하려면 Secrets에 RESEND_API_KEY, '
                    'KEYWORD_REQUEST_ADMIN_EMAIL, KEYWORD_REQUEST_FROM_EMAIL을 설정하세요. '
                    '발신 주소의 도메인은 Resend에서 인증해야 합니다.'
                )
            with st.form('request_email_notification_settings'):
                st.toggle(
                    '새 문의 등록 시 관리자 이메일 알림', key=setting_key,
                    disabled=not configured and not st.session_state[setting_key],
                )
                save_toggle = st.form_submit_button('알림 설정 저장')
            if save_toggle:
                try:
                    repository.save_request_email_notifications(
                        st.session_state[setting_key], access_token,
                    )
                    st.success('이메일 알림 설정을 저장했습니다.')
                except (StorageError, PermissionError) as exc:
                    st.error('이메일 알림 설정을 저장하지 못했습니다.')
                    st.caption(str(exc))
        except (StorageError, PermissionError) as exc:
            st.error('관리자 알림 설정을 불러오지 못했습니다. 문의용 DB 설정을 적용했는지 확인하세요.')
            st.caption(str(exc))

    try:
        requests = repository.load_keyword_requests(access_token)
    except (StorageError, PermissionError) as exc:
        st.error('문의 내역을 불러오지 못했습니다. 문의용 DB 설정과 RLS 정책을 확인하세요.')
        st.caption(str(exc))
        return

    if not requests:
        st.info('등록된 키워드 문의가 없습니다.')
        return
    display_rows = []
    for row in requests:
        request_id = str(row.get('id', '')).strip()
        display = {
            '접수번호': f"KR-{request_id[:8].upper()}",
            'kwd_no': row.get('kwd_no', ''),
            '키워드명': row.get('keyword_name', ''),
            '문의 유형': KEYWORD_REQUEST_TYPE_LABELS.get(row.get('request_type'), row.get('request_type', '')),
            '요청 상세 내용': row.get('request_detail', ''),
            '처리상태': row.get('status', '대기'),
            '관리자 답변': row.get('admin_reply', ''),
        }
        if is_admin():
            display['요청자 이메일'] = row.get('requester_email', '')
        display['접수 시각'] = format_keyword_request_time(row.get('created_at', ''))
        display_rows.append(display)

    epoch = st.session_state.setdefault('keyword_request_history_epoch', 0)
    table_state = _selectable_dataframe(
        pd.DataFrame(display_rows), hide_index=True, width='stretch',
        on_select='rerun', selection_mode='multi-row',
        alt='Keyword request history',
        key=f'keyword_request_history_{epoch}',
    )
    st.caption('문의 행을 선택하면 상세 내역과 댓글을 확인할 수 있습니다.')
    selected_rows = table_state.selection.rows
    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(requests):
            render_keyword_request_dialog(requests[selected_index], access_token)

    if len(requests) >= 1000:
        st.caption('최근 1,000건만 표시했습니다. 더 오래된 요청은 관리자에게 문의하세요.')

render_admin_login()

if not cloud_enabled() and is_admin():
    new_path = st.sidebar.text_input('저장 경로 변경', value=st.session_state.storage_path)
    if st.sidebar.button('경로 적용'):
        st.session_state.storage_path = new_path
        st.session_state.kw_df = load_db(Path(new_path))
        scan_existing_counters()

st.sidebar.caption(f'앱 버전 · {APP_VERSION}')

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
    MATCH_MODES['similar']: '등록 키워드와 입력의 Kiwi 내용어 토큰이 같으면 찾습니다. 승인 표현은 자동 분석을 보완합니다.',
    MATCH_MODES['partial']: '승인이나 단어 경계 검사 없이 연속된 글자 조각을 찾습니다. 최소 글자수를 직접 조절합니다.',
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
        '등록 키워드와 입력 문장을 Kiwi로 분석합니다.\n\n'
        '양쪽의 내용어 토큰 전체가 같으면 검출합니다.\n\n'
        '자동으로 나뉘지 않는 전문 용어는 관리자 승인 표현으로 보완합니다.\n\n'
        '예시) 등록 `노화방지` → `노화` + `방지`\n\n'
        '- O · `노화 피부` → `노화` 토큰으로 노화방지 검출\n'
        '- X · 등록 `안티에이징` / 입력 `티에이` → 동일 토큰 없음\n'
        '- O · 등록 `안티에이징` / 입력 `에이징 관리` → 에이징 승인 시 검출\n\n'
        '괄호 설명 제외를 끄면 괄호 안 단어도 비교합니다.\n\n'
        '내용어 한 개만 같아도 관련 후보가 됩니다.\n\n동의어·위반 여부는 판단하지 않습니다.'),
    MATCH_MODES['partial']: (
        '단어 의미와 경계에 관계없이 연속된 글자 조각을 찾습니다.\n\n'
        '승인 표현과 Kiwi 경계 검사는 적용하지 않습니다.\n\n'
        '글자수를 늘리면 짧은 조각으로 인한 결과를 줄일 수 있습니다.\n\n'
        '예시) 등록 키워드: `안티에이징`\n\n'
        '- O · 최소 2글자 / 입력 `안티` → 실제 일치 `안티`\n'
        '- X · 최소 3글자 / 입력 `안티` → 미검출\n'
        '- O · 최소 3글자 / 입력 `에이징` → 실제 일치 `에이징`\n'
        '- X · 최소 4글자 / 입력 `에이징` → 미검출'),
}


def matching_mode_option_label(mode):
    # Inline help keeps the native radio group and its keyboard behavior.
    description = html.escape(_numbered_help(MATCH_MODE_DETAILS[mode].replace('`', '')), quote=True)
    description = description.replace('[', '&#91;').replace(']', '&#93;').replace('\n', '&#10;')
    return f'{MATCH_MODE_LABELS[mode]} :help[{description}]'


def _numbered_help(text):
    """Split help copy into numbered items, one sentence per line."""
    import re

    parts = re.split(r'(?<=[.!?])\s+|\n+', str(text).strip())
    items = [part.strip().lstrip('- ').strip() for part in parts if part.strip()]
    return '\n\n'.join(f'{index}. {item}' for index, item in enumerate(items, start=1))


def invalidate_analysis_result():
    st.session_state['analysis_show'] = False


def render_matching_rules_summary(config):
    selected = st.session_state.get('match_mode', MATCH_MODES[config.mode])
    summary = [
        '키워드 매칭 방식: ' + MATCH_MODE_LABELS.get(selected, '기존 변형 규칙 검색(API)')
    ]
    if config.mode == 'partial':
        summary.append(f'최소 일치 글자수: {config.partial_min_len}글자')
    for name, (label, _) in MATCH_NORMALIZATION_OPTIONS.items():
        summary.append(label + ': ' + ('켜짐' if config.normalization_options()[name] else '꺼짐'))
    if config.mode == 'similar':
        summary.extend([
            '양쪽 Kiwi 내용어 토큰 전체 비교 + 승인 표현 보완 + 원문 단어 경계 검사',
            '조사·어미 허용 목록과 임의 글자 조각 검색은 적용하지 않습니다.',
        ])
    else:
        summary.append('뒤에 붙는 말 허용 목록: 이 검사 방식에는 적용하지 않음')
    if config.normalization_options()['normalize_symbols']:
        summary.append('비교 시 처리할 기호: ' + (' · '.join(config.ignored_symbols) or '없음'))
    else:
        summary.append('기호 처리가 꺼져 있어 공통 기호 목록은 적용하지 않습니다.')
    summary.append('목록은 관리자 공통 설정입니다. 분석 실행 시 저장된 최신 규칙을 다시 불러옵니다.')
    st.caption('현재 선택한 매칭방식&매칭옵션', help=_numbered_help('\n\n'.join(summary)))


def load_approved_partials():
    if cloud_enabled():
        return SupabaseRepository().load_setting(SETTING_NAME, {})
    path = Path(__file__).with_name('approved_partial_expressions_v272.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def render_approved_partial_rules():
    _require_admin()
    with st.expander('일부 일치 — 승인된 부분 표현', expanded=False):
        st.caption('FIXED275 일부 일치에만 적용합니다. 공통 내용어 토큰은 승인 없이 자동 검사합니다.\n\n'
                   '자동 분석에서 누락된 의미 있는 부분 표현만 키워드별로 승인하세요.\n\n'
                   '예시) 안티에이징 → 에이징. 티에이 같은 무의미한 조각은 승인하지 마세요.\n\n'
                   '등록명을 바꾸면 기존 승인은 적용되지 않습니다.')
        df = st.session_state.kw_df
        if df.empty:
            st.info('먼저 키워드를 등록하세요.')
            return
        try:
            saved = load_approved_partials()
            names = dict(zip(df['kwd_no'].astype(str), df['키워드명'].astype(str)))
            # The visible option label starts with kwd_no, so sort by that displayed identifier.
            keyword_codes = sorted(names, key=lambda value: (value.casefold(), names[value].casefold()))
            code = st.selectbox('승인할 키워드', keyword_codes,
                                format_func=lambda value: f'{value} · {names[value]}',
                                key='approved_partial_keyword')
            term = names[code]
            entry = saved.get(code, {})
            values = entry.get('expressions', []) if entry.get('term') == term else []
            version = st.session_state.get('approved_partial_editor_version', 0)
            with st.form('approved_partial_form'):
                raw = st.text_area('승인할 부분 표현 — 한 줄에 하나', value='\n'.join(values),
                                   key=f'approved_partial_text_{code}_{term}_{version}')
                submit = st.form_submit_button('승인 표현 저장')
            if submit:
                _require_admin()
                expressions = validate_expressions(term, raw.splitlines(), _matching_config())
                # Refresh other keywords before replacing this keyword's approval.
                latest = load_approved_partials()
                latest[code] = {'term': term, 'expressions': expressions}
                if cloud_enabled():
                    SupabaseRepository().save_setting(SETTING_NAME, latest)
                else:
                    path = Path(__file__).with_name('approved_partial_expressions_v272.json')
                    temporary = path.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding='utf-8')
                    temporary.replace(path)
                invalidate_analysis_result()
                st.session_state.approved_partial_editor_version = version + 1
                st.session_state.matching_rules_notice = '승인 표현을 저장했습니다. 다음 분석부터 적용됩니다.'
                st.rerun()
        except (StorageError, PermissionError, ValueError, OSError) as exc:
            st.error(f'승인 표현을 불러오거나 저장하지 못했습니다: {exc}')


def render_common_matching_rules():
    _require_admin()
    st.caption('저장한 규칙은 이후 분석부터 모든 사용자에게 적용됩니다.\n\n이번 분석 옵션은 분석하기 탭에서 선택합니다.')
    if message := st.session_state.pop('matching_rules_notice', None):
        st.success(message)
    render_approved_partial_rules()
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
    _selectable_dataframe(pd.DataFrame([{
        '이메일': user['email'], '역할': labels.get(user['role'], '앱 권한 미지정'),
        '이메일 확인': '완료' if user['email_confirmed'] else '미완료',
    } for user in users]), hide_index=True, width='stretch', alt='Managed user accounts')
    by_id = {user['id']: user for user in users}
    account_ids = sorted(by_id, key=lambda uid: (by_id[uid]['email'] or uid).casefold())
    target_id = st.selectbox('변경할 계정', options=account_ids,
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
        role_options = sorted(labels, key=lambda value: labels[value])
        role = st.selectbox('변경할 역할', options=role_options,
                            index=role_options.index(target['role']),
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


import unicodedata
import sys
import os
import importlib
import auxiliary_analysis as _auxiliary_analysis


def _get_auxiliary_analysis_function(name):
    """Reload stale helper code retained across Streamlit reruns."""
    function = getattr(_auxiliary_analysis, name, None)
    if (getattr(_auxiliary_analysis, 'UNMATCHED_SURFACE_LIMIT_REVISION', 0) < 1
            or not callable(function)):
        importlib.invalidate_caches()
        importlib.reload(_auxiliary_analysis)
        function = getattr(_auxiliary_analysis, name, None)
    if not callable(function):
        raise ImportError(f"auxiliary_analysis.py에 {name} 함수가 없습니다.")
    return function

import ocr_keyword_import as _ocr_keyword_import

_OCR_IMPORTS = ("extract_text_lines", "make_image_preview_data", "render_text_selectable_image")
if (getattr(_ocr_keyword_import, "OCR_OVERLAY_REVISION", None) != 2
        or any(not callable(getattr(_ocr_keyword_import, name, None)) for name in _OCR_IMPORTS)):
    # Streamlit Cloud can rerun the new entrypoint while retaining an older
    # helper module in sys.modules, even when its function names still match.
    importlib.invalidate_caches()
    _ocr_keyword_import = importlib.reload(_ocr_keyword_import)
_missing_ocr_imports = [
    name for name in _OCR_IMPORTS
    if not callable(getattr(_ocr_keyword_import, name, None))
]
if _missing_ocr_imports:
    raise ImportError(
        "ocr_keyword_import is missing required functions after reload: "
        + ", ".join(_missing_ocr_imports)
    )
extract_text_lines = _ocr_keyword_import.extract_text_lines
make_image_preview_data = _ocr_keyword_import.make_image_preview_data
render_text_selectable_image = _ocr_keyword_import.render_text_selectable_image


@st.cache_resource(show_spinner="Loading the Korean OCR model…")
def _load_korean_ocr():
    """Initialize PaddleOCR once per Streamlit process and reuse the pipeline."""
    # Avoid repeated PaddleX repository initialization during Streamlit reruns.
    os.environ["PADDLE_PDX_EAGER_INIT"] = "False"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang="korean",
        ocr_version="PP-OCRv5",
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _ocr_normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _ocr_select_options(values):
    options = set()
    for value in values:
        if value is None:
            continue
        option = str(value).strip()
        if not option or option.casefold() in {"none", "nan"} or "(직접 입력)" in option:
            continue
        options.add(option)
    return sorted(options) or ["-"]


def _ocr_options_for_column(frame, column, configured_options):
    values = []
    if column in frame.columns:
        values = frame[column].dropna().astype(str).str.strip().tolist()
    return _ocr_select_options(values + list(configured_options or []))


def _update_ocr_editor_approvals(editor_key, candidates_key, version_key, select_all_key):
    candidates = [dict(row) for row in st.session_state.get(candidates_key, [])]
    widget_state = st.session_state.get(editor_key) or {}
    edited_rows = {
        int(index): changes
        for index, changes in (widget_state.get("edited_rows") or {}).items()
    }
    editable_columns = {"term", "category", "risk", "detail", "evidence", "alternative"}
    for index, row in enumerate(candidates):
        changes = edited_rows.get(index, {})
        for column, value in changes.items():
            if column in editable_columns:
                row[column] = value
        row["approved"] = bool(st.session_state.get(select_all_key, False))
    selected = bool(st.session_state.get(select_all_key, False))
    for row in candidates:
        row["approved"] = selected
    st.session_state[candidates_key] = candidates
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


def _clear_ocr_results_on_upload(candidates_key, editor_version_key, file_results_key, preview_page_key, upload_widget_key, stored_uploads_key):
    # Keep UploadedFile references outside the widget state so tab switches do not
    # discard the source images or their previews.
    st.session_state[stored_uploads_key] = list(st.session_state.get(upload_widget_key) or [])
    st.session_state[candidates_key] = []
    st.session_state[file_results_key] = []
    st.session_state[preview_page_key] = 0
    st.session_state[editor_version_key] = int(st.session_state.get(editor_version_key, 0)) + 1
    st.session_state.pop('ocr_keyword_collection_id', None)


def _persist_ocr_candidate_edits(editor_key, candidates_key, select_all_key):
    """Copy data-editor changes into durable per-session candidate data."""
    widget_state = st.session_state.get(editor_key) or {}
    edited_rows = widget_state.get("edited_rows", {})
    candidates = st.session_state.get(candidates_key, [])
    editable_columns = {"term", "category", "risk", "detail", "evidence", "alternative", "approved"}
    for index, changes in edited_rows.items():
        if not 0 <= index < len(candidates):
            continue
        for column, value in changes.items():
            if column in editable_columns:
                candidates[index][column] = bool(value) if column == "approved" else value
    st.session_state[candidates_key] = candidates
    st.session_state[select_all_key] = bool(candidates) and all(
        bool(row.get("approved", False)) for row in candidates)


def _set_unmatched_select_all(recommendation_ids, checkbox_key):
    selected_ids = recommendation_ids if st.session_state.get(checkbox_key, False) else []
    st.session_state['unmatched_recommendation_selected_ids'] = list(selected_ids)
    st.session_state['unmatched_recommendation_version'] = int(
        st.session_state.get('unmatched_recommendation_version', 0)) + 1


def _persist_unmatched_editor(editor_key, recommendations, selection_column, checkbox_key):
    edited_rows = (st.session_state.get(editor_key) or {}).get('edited_rows') or {}
    saved_edits = st.session_state.setdefault('unmatched_recommendation_edits', {})
    selected_ids = set(st.session_state.get('unmatched_recommendation_selected_ids', []))
    recommendation_ids = []
    for index, recommendation in enumerate(recommendations):
        recommendation_id = recommendation['recommendation_id']
        recommendation_ids.append(recommendation_id)
        changes = edited_rows.get(index, edited_rows.get(str(index), {}))
        if changes:
            saved_edits.setdefault(recommendation_id, {}).update(changes)
        if selection_column in changes:
            if changes[selection_column]:
                selected_ids.add(recommendation_id)
            else:
                selected_ids.discard(recommendation_id)
    selected_ids.intersection_update(recommendation_ids)
    st.session_state['unmatched_recommendation_selected_ids'] = list(selected_ids)
    st.session_state[checkbox_key] = bool(recommendation_ids) and all(
        recommendation_id in selected_ids for recommendation_id in recommendation_ids)


def _persist_keyword_editor(editor_key, base_key, draft_key, checkbox_key, selection_column):
    frame = pd.DataFrame(st.session_state.get(base_key, []))
    widget_state = st.session_state.get(editor_key) or {}
    for index, changes in (widget_state.get('edited_rows') or {}).items():
        index = int(index)
        if 0 <= index < len(frame):
            for column, value in changes.items():
                if column in frame.columns:
                    frame.at[index, column] = value
    deleted_rows = sorted(
        (int(index) for index in widget_state.get('deleted_rows', [])), reverse=True)
    if deleted_rows:
        frame = frame.drop(index=deleted_rows).reset_index(drop=True)
    added_rows = widget_state.get('added_rows') or []
    if added_rows:
        frame = pd.concat([frame, pd.DataFrame(added_rows)], ignore_index=True)
    if selection_column in frame.columns:
        frame[selection_column] = frame[selection_column].fillna(False).astype(bool)
    draft = frame.to_dict('records')
    st.session_state[draft_key] = draft
    st.session_state[checkbox_key] = bool(draft) and all(
        bool(row.get(selection_column, False)) for row in draft)


def _set_keyword_editor_select_all(draft_key, base_key, selection_column, version_key, checkbox_key):
    rows = [dict(row) for row in st.session_state.get(draft_key, st.session_state.get(base_key, []))]
    selected = bool(st.session_state.get(checkbox_key, False))
    for row in rows:
        row[selection_column] = selected
    st.session_state[draft_key] = rows
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


def _reset_ocr_analysis(candidates_key, editor_version_key, image_version_key, file_results_key, preview_page_key, stored_uploads_key):
    st.session_state[candidates_key] = []
    st.session_state[file_results_key] = []
    st.session_state[preview_page_key] = 0
    st.session_state[editor_version_key] = int(st.session_state.get(editor_version_key, 0)) + 1
    st.session_state[image_version_key] = int(st.session_state.get(image_version_key, 0)) + 1
    st.session_state[stored_uploads_key] = []
    st.session_state.pop('ocr_keyword_collection_id', None)


def _clear_unmatched_review():
    st.session_state['unmatched_candidate_recommendations'] = []
    st.session_state['unmatched_recommendation_hidden_ids'] = []
    st.session_state['unmatched_recommendation_selected_ids'] = []
    st.session_state['unmatched_recommendation_edits'] = {}
    st.session_state['unmatched_recommendation_version'] = int(
        st.session_state.get('unmatched_recommendation_version', 0)) + 1
    st.session_state.pop('unmatched_export_csv', None)
    st.session_state.pop('unmatched_candidate_review', None)
    st.session_state['unmatched_candidate_review_revision'] = int(
        st.session_state.get('unmatched_candidate_review_revision', 0)) + 1


def _flush_unmatched_collections():
    pending = st.session_state.setdefault('unmatched_pending_collections', {})
    for analysis_id, candidates in list(pending.items()):
        try:
            SupabaseRepository().collect_unmatched_terms(analysis_id, candidates)
        except Exception:
            logging.exception('Could not persist unmatched candidates')
            st.warning('미매칭 후보를 DB에 저장하지 못했습니다. 수집 저장 재시도로 다시 저장하세요.')
            return False
        pending.pop(analysis_id)
        _clear_unmatched_review()
    return True


def _collect_unmatched_text(text, coverage_matches=None, analysis_id=None):
    if coverage_matches is None:
        config = _matching_config()
        if cloud_enabled():
            config = load_matching_config(SupabaseRepository(), config)
        coverage_matches = [] if st.session_state.kw_df.empty else match_text(
            text, st.session_state.kw_df, config=config,
            approved_partials=load_approved_partials() if config.mode == 'similar' else None)
    extract_surfaces = _get_auxiliary_analysis_function('extract_unmatched_term_surfaces')
    candidates = extract_surfaces(text, coverage_matches, limit=None)
    if cloud_enabled():
        # Only expressions/counts and an anonymous retry ID survive this call.
        pending = st.session_state.setdefault('unmatched_pending_collections', {})
        pending[str(analysis_id or uuid4())] = candidates
        return _flush_unmatched_collections()
    # CSV mode is local development; shared persistence requires the server DB.
    pool = st.session_state.setdefault('unmatched_candidate_pool', {})
    for row in candidates:
        previous = pool.get(row['surface_key'])
        if previous:
            previous['occurrences'] += row['occurrences']
        else:
            pool[row['surface_key']] = dict(row)
    _clear_unmatched_review()
    return True


def _prepare_ocr_candidate_analysis(editor_key, candidates_key, analysis_tab_label):
    widget_state = st.session_state.get(editor_key) or {}
    edited_rows = widget_state.get("edited_rows", {})
    terms = []
    candidates = st.session_state.get(candidates_key, [])
    for index, row in enumerate(candidates):
        changes = edited_rows.get(index, {})
        if not bool(changes.get("approved", row.get("approved", False))):
            continue
        term = str(changes.get("term", row.get("term", ""))).strip()
        if term:
            try:
                occurrences = max(1, int(row.get("occurrences", 1) or 0))
            except (TypeError, ValueError, OverflowError):
                occurrences = 1
            terms.extend([term] * occurrences)
    text = "\n".join(terms)
    if not text:
        st.session_state["ocr_analysis_error"] = "승인 체크된 OCR 후보가 없어 분석할 수 없습니다."
        return
    existing_text = str(st.session_state.get("analysis_input_text", ""))
    existing_content = existing_text.rstrip("\r\n")
    combined_text = f"{existing_content}\n\n{text}" if existing_content.strip() else text
    if len(combined_text) > 20000:
        st.session_state["ocr_analysis_error"] = "기존 스크립트와 OCR 후보를 합친 분석 입력은 20,000자까지 가능합니다. 내용을 줄인 뒤 다시 시도하세요."
        return
    st.session_state.pop("ocr_analysis_error", None)
    st.session_state["analysis_input_text"] = combined_text
    st.session_state["analysis_auto_run_pending"] = True
    st.session_state["main_app_tabs"] = analysis_tab_label


def render_image_ocr_tab():
    ocr_analysis_error = st.session_state.pop("ocr_analysis_error", None)
    if ocr_analysis_error:
        st.error(ocr_analysis_error)
    st.subheader("이미지 OCR분석")
    st.caption("\uc774\ubbf8\uc9c0\uc5d0\uc11c \ud0a4\uc6cc\ub4dc \ud6c4\ubcf4\ub9cc \ucd94\ucd9c\ud569\ub2c8\ub2e4. \ud544\uc218 \ubd84\ub958 \ud56d\ubaa9\uc744 \uac80\ud1a0\xb7\uc2b9\uc778\ud55c \ub4a4 DB\uc5d0 \uc800\uc7a5\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.")
    image_version_key = "ocr_keyword_image_version"
    stored_uploads_key = "ocr_keyword_uploaded_files"
    image_version = st.session_state.get(image_version_key, 0)
    st.markdown("""
    <style>
    div[class*="st-key-ocr_keyword_image_"] {
        width: min(100%, 720px) !important;
        max-width: 720px !important;
        min-width: 0 !important;
        box-sizing: border-box !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploader"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin: 0 !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploaderDropzone"]:not(:has(button[aria-label="Add files"])) {
        align-items: center !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploaderDropzone"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        height: auto !important;
        min-height: 62px !important;
        box-sizing: border-box !important;
        padding: 0.35rem !important;
        border-radius: 8px !important;
        background: #f0f2f6 !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploaderDropzone"] > * {
        min-width: 0 !important;
        max-width: 100% !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploaderDropzoneInstructions"] {
        order: 1 !important;
        min-width: 0 !important;
        white-space: normal !important;
        font-size: 0.72rem !important;
    }
    div[class*="st-key-ocr_keyword_image_"] [data-testid="stFileUploaderDropzone"] button[aria-label="Add files"] {
        order: 0 !important;
        width: auto !important;
        min-width: 6.5rem !important;
        max-width: none !important;
        height: 2rem !important;
        min-height: 2rem !important;
        padding: 0.25rem 0.65rem !important;
        font-size: 0.875rem !important;
        white-space: nowrap !important;
    }
    .st-key-ocr-empty-state {
        width: min(100%, 720px) !important;
        max-width: 720px !important;
        min-width: 0 !important;
        padding: 0 !important;
        margin: -0.55rem 0 0 !important;
    }
    .st-key-ocr-empty-state .ocr-empty-box {
        width: 100% !important;
        height: 62px !important;
        min-height: 62px !important;
        box-sizing: border-box !important;
        display: flex !important;
        align-items: center !important;
        padding: 0 0.75rem !important;
        margin: 0 !important;
        border-radius: 8px !important;
        background: #e8f1ff !important;
        color: #0061b0 !important;
        font-size: 0.95rem !important;
    }
    @media (max-width: 768px) {
        div[class*="st-key-ocr_keyword_image_"],
        .st-key-ocr-empty-state {
            width: 100% !important;
            max-width: 100% !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    with st.container(key="ocr-upload-zone"):
        uploaded = st.file_uploader(
            "키워드 이미지 업로드",
            type=["png", "jpg", "jpeg", "webp", "bmp"],
            accept_multiple_files=True,
            max_upload_size=20,
            key=f"ocr_keyword_image_{image_version}",
            on_change=_clear_ocr_results_on_upload,
            args=("ocr_keyword_candidates", "ocr_keyword_editor_version", "ocr_keyword_file_results", "ocr_keyword_preview_page", f"ocr_keyword_image_{image_version}", stored_uploads_key),
        )
    # The file uploader may lose its widget value when its tab is not rendered.
    # Prefer the session copy; it is cleared only on a new upload, reset, or save.
    if uploaded:
        st.session_state[stored_uploads_key] = list(uploaded)
    uploaded_files = st.session_state.get(stored_uploads_key) or uploaded or []
    max_ocr_images = 5
    max_ocr_total_bytes = 50 * 1024 * 1024
    total_upload_bytes = sum(file.size for file in uploaded_files)
    upload_is_valid = bool(uploaded_files) and len(uploaded_files) <= max_ocr_images and total_upload_bytes <= max_ocr_total_bytes
    if uploaded_files:
        st.caption(f"\ucca8\ubd80\ud55c \uc774\ubbf8\uc9c0: {len(uploaded_files)}\uc7a5 / \ucd1d {total_upload_bytes / (1024 * 1024):.1f}MB (\ucd5c\ub300 5\uc7a5, \ucd1d 50MB)")
        st.caption("\ud30c\uc77c\ubcc4 \ud55c\ub3c4\ub294 20MB\uc785\ub2c8\ub2e4. \uc120\ud0dd\ud55c \ud30c\uc77c\uc740 \ud55c \uc7a5\uc529 \ucc28\ub840\ub300\ub85c OCR\ucc98\ub9ac\ud569\ub2c8\ub2e4.")
        if len(uploaded_files) > max_ocr_images:
            st.error(f"\uc774\ubbf8\uc9c0\ub294 \ud55c \ubc88\uc5d0 \ucd5c\ub300 {max_ocr_images}\uc7a5\uae4c\uc9c0 \uc5c5\ub85c\ub4dc\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.")
        if total_upload_bytes > max_ocr_total_bytes:
            st.error("\uc5c5\ub85c\ub4dc \uc804\uccb4 \uc6a9\ub7c9\uc740 50MB\uae4c\uc9c0 \uac00\ub2a5\ud569\ub2c8\ub2e4. \ud30c\uc77c \uc218\ub97c \uc904\uc774\uac70\ub098 \uc774\ubbf8\uc9c0\ub97c \uc555\ucd95\ud574\uc11c \uc62c\ub824\uc8fc\uc138\uc694.")
        file_results_by_index = {
            int(result.get("index", index)): result
            for index, result in enumerate(st.session_state.get("ocr_keyword_file_results", []))
            if str(result.get("index", index)).isdigit()
        }
        has_selectable_ocr = any(
            result.get("preview_data") and any(line.get("bbox") for line in result.get("lines", []))
            for result in file_results_by_index.values()
        )
        if has_selectable_ocr:
            st.caption("이미지 위 인식 글자를 드래그해 선택한 뒤 Ctrl+C로 복사할 수 있습니다.")

        run_ocr_clicked = st.button(
            "OCR \ubd84\uc11d \uc2e4\ud589",
            type="primary",
            key="ocr_keyword_run",
            disabled=not upload_is_valid,
        )

        def render_ocr_preview(image_file, image_index):
            result = file_results_by_index.get(image_index, {})
            lines = result.get("lines", [])
            selectable_lines = [line for line in lines if line.get("bbox")]
            preview_data = result.get("preview_data")
            caption = f"{image_file.name} ({image_index + 1}/{len(uploaded_files)})"
            if preview_data and selectable_lines:
                overlay_rendered = render_text_selectable_image(
                    preview_data,
                    result.get("image_width", 1),
                    result.get("image_height", 1),
                    selectable_lines,
                    alt=caption,
                    key=f"ocr_selectable_image_{image_version}_{image_index}",
                )
                if not overlay_rendered:
                    st.image(image_file.getvalue(), caption=caption, width="stretch")
                    st.caption("이미지 텍스트 선택 레이어를 불러오지 못해 기본 미리보기를 표시합니다.")
                elif len(selectable_lines) < len(lines):
                    st.caption("일부 인식 문장은 위치 정보를 얻지 못해 이미지에서 선택할 수 없습니다.")
            else:
                st.image(image_file.getvalue(), caption=caption, width="stretch")
                if lines and not selectable_lines:
                    st.caption("인식 결과의 위치 정보가 없어 이미지 위에서 선택할 수 없습니다.")
                elif result.get("preview_error"):
                    st.caption("선택 레이어 미리보기를 만들지 못했습니다. OCR 후보는 유지됩니다.")

        image_column, _ = st.columns([0.6, 0.4])
        with image_column:
            page_size = 2
            page_count = (len(uploaded_files) + page_size - 1) // page_size
            page_key = "ocr_keyword_preview_page"
            page_index = max(0, min(st.session_state.get(page_key, 0), page_count - 1))
            if page_count > 1:
                previous_col, page_col, next_col = st.columns([1, 2, 1])
                if previous_col.button("\u2039 \uc774\uc804", key="ocr_preview_previous", disabled=page_index == 0):
                    page_index -= 1
                if next_col.button("\ub2e4\uc74c \u203a", key="ocr_preview_next", disabled=page_index >= page_count - 1):
                    page_index += 1
                page_col.markdown(f"<div style='text-align:center;padding-top:0.35rem'>{page_index + 1} / {page_count}</div>", unsafe_allow_html=True)
                st.session_state[page_key] = page_index
            first_image_index = page_index * page_size
            preview_files = uploaded_files[first_image_index:first_image_index + page_size]
            if len(preview_files) == 1:
                image_file = preview_files[0]
                render_ocr_preview(image_file, first_image_index)
            else:
                preview_columns = st.columns(2)
                for offset, image_file in enumerate(preview_files):
                    with preview_columns[offset]:
                        render_ocr_preview(image_file, first_image_index + offset)
        if len(uploaded_files) > 1:
            with st.expander(f"\ucca8\ubd80 \uc774\ubbf8\uc9c0 \ud30c\uc77c\uba85 {len(uploaded_files)}\uac1c \ud655\uc778"):
                for image_file in uploaded_files:
                    st.write(f"\u2022 {image_file.name} ({image_file.size / (1024 * 1024):.1f}MB)")
        if run_ocr_clicked:
            try:
                ocr_engine = _load_korean_ocr()
            except ImportError as exc:
                logging.exception("PaddleOCR import failed")
                if sys.version_info >= (3, 14):
                    st.error("\ud604\uc7ac Python 3.14\uc5d0\uc11c\ub294 PaddlePaddle\uc744 \uc0ac\uc6a9\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. Python 3.13 \uc774\ud558 \uac00\uc0c1\ud658\uacbd\uc5d0\uc11c \uae30\ubcf8 requirements.txt\uc640 requirements-ocr.txt\ub97c \uc124\uce58\ud574\uc57c \ud569\ub2c8\ub2e4.")
                else:
                    st.error(f"PaddleOCR \ub610\ub294 \ub0b4\ubd80 \uc758\uc874\uc131\uc744 \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4: {exc}")
            except Exception as exc:
                logging.exception("OCR engine initialization failed")
                st.error(f"OCR \uc900\ube44 \uc911 \uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4: {exc}")
            else:
                unique_rows = {}
                file_results = []
                with st.spinner(f"{len(uploaded_files)}\uc7a5\uc758 \uc774\ubbf8\uc9c0\ub97c \uc21c\ucc28\ub85c OCR \ucc98\ub9ac\ud558\uace0 \uc788\uc2b5\ub2c8\ub2e4..."):
                    for image_index, image_file in enumerate(uploaded_files):
                        try:
                            ocr_rows = extract_text_lines(image_file.getvalue(), ocr_engine)
                            preview_data = None
                            image_width = image_height = 1
                            preview_error = ""
                            try:
                                preview_data, image_width, image_height = make_image_preview_data(image_file.getvalue())
                            except Exception as exc:
                                preview_error = str(exc)
                                logging.exception("OCR selectable-image preview generation failed")
                            file_results.append({
                                "index": image_index,
                                "name": image_file.name,
                                "count": len(ocr_rows),
                                "error": "",
                                "lines": ocr_rows,
                                "preview_data": preview_data,
                                "image_width": image_width,
                                "image_height": image_height,
                                "preview_error": preview_error,
                            })
                            for row in ocr_rows:
                                text = unicodedata.normalize("NFKC", str(row["text"])).strip()
                                normalized = _ocr_normalize(text)
                                confidence = float(row["confidence"])
                                if normalized:
                                    candidate = unique_rows.setdefault(normalized, {
                                        "term": text, "confidence": confidence, "occurrences": 0,
                                    })
                                    if confidence >= 0.60:
                                        candidate["occurrences"] += 1
                                    if confidence > candidate["confidence"]:
                                        candidate.update(term=text, confidence=confidence)
                        except Exception as exc:
                            file_results.append({"index": image_index, "name": image_file.name, "count": 0, "error": str(exc)})
                st.session_state.ocr_keyword_file_results = file_results
                st.session_state.ocr_keyword_candidates = [
                    {
                        **row, "category": "", "risk": "", "alternative": "-",
                        "detail": "", "evidence": "", "approved": row["confidence"] >= 0.60,
                        "duplicate": "",
                    }
                    for row in unique_rows.values()
                ]
                st.session_state.ocr_keyword_editor_version = st.session_state.get("ocr_keyword_editor_version", 0) + 1
                st.session_state.pop('ocr_keyword_collection_id', None)
                st.session_state.pop('ocr_unmatched_extraction_failed', None)
                # The preview above rendered before these results existed.
                # Refresh it immediately; reuse the saved OCR results.
                st.rerun()

    for result in st.session_state.get("ocr_keyword_file_results", []):
        if result["error"]:
            st.error(f"{result['name']}: OCR \ucc98\ub9ac \uc2e4\ud328 - {result['error']}")
        elif result["count"]:
            st.caption(f"{result['name']}: OCR \uc778\uc2dd \uc644\ub8cc ({result['count']}\uac1c \ud14d\uc2a4\ud2b8)")
        else:
            st.warning(f"{result['name']}: \uc778\uc2dd\ud55c \ud14d\uc2a4\ud2b8\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.")

    candidates = st.session_state.get("ocr_keyword_candidates", [])
    if not candidates:
        with st.container(key="ocr-empty-state"):
            st.markdown(
                '<div class="ocr-empty-box">'
                '이미지를 업로드하고 OCR을 실행하면 검토할 후보가 여기에 표시됩니다.'
                '</div>',
                unsafe_allow_html=True,
            )
        return

    df = pd.DataFrame(candidates)
    df["confidence"] = (df["confidence"] * 100).round().astype(int)
    base_df = st.session_state.kw_df.copy()
    # DB_COLS order: kwd_no, keyword, category, risk, alternative, detail, evidence, ...
    _, term_col, category_col, risk_col, alt_col, detail_col, evidence_col = DB_COLS[:7]
    existing_pairs = {
        (_ocr_normalize(row.get(term_col, "")), _ocr_normalize(row.get(category_col, "")))
        for row in base_df.to_dict("records")
    }
    cat_options = _ocr_options_for_column(base_df, category_col, st.session_state.get("opt_categories", DEFAULT_CATEGORIES))
    risk_options = _ocr_options_for_column(base_df, risk_col, st.session_state.get("opt_risks", RISK_OPTIONS))
    detail_options = _ocr_options_for_column(base_df, detail_col, st.session_state.get("opt_details", DEFAULT_DETAIL_CRITERIA))
    evidence_options = _ocr_options_for_column(base_df, evidence_col, st.session_state.get("opt_evidences", DEFAULT_EVIDENCE_TYPES))
    alt_options = _ocr_options_for_column(base_df, alt_col, st.session_state.get("opt_alt_terms", DEFAULT_ALT_KEYWORDS))
    version = st.session_state.get("ocr_keyword_editor_version", 0)
    editor_key = f"ocr_keyword_editor_{version}"
    select_all_key = f"ocr_keyword_select_all_{version}"
    st.session_state.setdefault(
        select_all_key,
        bool(candidates) and all(bool(row.get("approved", False)) for row in candidates),
    )
    st.button(
        "OCR \ubd84\uc11d \ucd08\uae30\ud654",
        key=f"ocr_keyword_reset_{version}",
        on_click=_reset_ocr_analysis,
        args=("ocr_keyword_candidates", "ocr_keyword_editor_version", image_version_key, "ocr_keyword_file_results", "ocr_keyword_preview_page", stored_uploads_key),
    )
    table_key = f"ocr_keyword_table_{version}"
    st.markdown(
        f"""
<style>
div.st-key-{table_key} {{ position: relative; }}
div.st-key-{table_key} div.st-key-{select_all_key} {{
    position: relative !important;
    top: 38px;
    left: 20px;
    z-index: 20;
    width: 20px;
    height: 20px;
    margin: 0;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    ocr_table = st.container(key=table_key)
    ocr_table.checkbox(
        "OCR 후보 전체 선택/해제",
        key=select_all_key,
        on_change=_update_ocr_editor_approvals,
        args=(editor_key, "ocr_keyword_candidates", "ocr_keyword_editor_version", select_all_key),
        disabled=not candidates,
        label_visibility="collapsed",
    )
    edited = ocr_table.data_editor(
        df,
        alt="OCR-extracted keyword candidates",
        key=editor_key,
        on_change=_persist_ocr_candidate_edits,
        args=(editor_key, "ocr_keyword_candidates", select_all_key),
        width="stretch",
        hide_index=True,
        disabled=["confidence"],
        column_order=["approved", "term", "confidence", "category", "risk", "detail", "evidence", "alternative"],
        column_config={
            "term": st.column_config.TextColumn("키워드명", required=True),
            "confidence": st.column_config.NumberColumn("OCR 신뢰도(%)", format="%d%%"),
            "category": st.column_config.SelectboxColumn("상품 카테고리", options=cat_options, required=True),
            "risk": st.column_config.SelectboxColumn("리스크 등급", options=risk_options, required=True),
            "detail": st.column_config.SelectboxColumn("심의기준", options=detail_options, required=True),
            "evidence": st.column_config.SelectboxColumn("증빙자료 유형", options=evidence_options, required=True),
            "alternative": st.column_config.SelectboxColumn("대체키워드", options=alt_options),
            "approved": st.column_config.CheckboxColumn("\u200b", width=56, pinned=True, default=False),
        },
    )
    candidate_pairs = [(_ocr_normalize(row.term), _ocr_normalize(row.category)) for row in edited.itertuples()]
    duplicate_names = [
        str(row.term) for row, pair in zip(edited.itertuples(), candidate_pairs)
        if pair in existing_pairs or candidate_pairs.count(pair) > 1
    ]
    if duplicate_names:
        st.warning("기존 DB 또는 후보끼리 중복된 항목: " + ", ".join(dict.fromkeys(duplicate_names)))
    st.caption("신뢰도가 60% 미만인 후보는 기본 선택 해제 상태입니다. 모든 후보를 직접 검토하세요.")
    approved = edited[edited["approved"].fillna(False).astype(bool)].copy()
    analysis_terms = approved["term"].fillna("").astype(str).str.strip()
    analysis_text = "\n".join(term for term in analysis_terms.tolist() if term)
    analysis_tab_label = next(label for key, label in tab_specs if key == "analysis")
    st.button(
        "OCR 후보 텍스트 분석 및 하이라이트 미리보기",
        key="ocr_keyword_preview_analysis",
        on_click=_prepare_ocr_candidate_analysis,
        args=(editor_key, "ocr_keyword_candidates", analysis_tab_label),
        disabled=not analysis_text or len(analysis_text) > 20000,
        help="승인 체크된 OCR 후보만 분석 입력란에 보내고 기존 키워드 DB로 분석합니다.",
    )
    if st.button("선택 후보 승인 및 DB 저장", type="primary", key="ocr_keyword_save", disabled=approved.empty):
        approved["term"] = approved["term"].fillna("").astype(str).str.strip()
        for column in ["category", "risk", "detail", "evidence"]:
            approved[column] = approved[column].fillna("").astype(str).str.strip()
        missing = approved[
            approved[["term", "category", "risk", "detail", "evidence"]].eq("").any(axis=1)
        ]
        if not missing.empty:
            st.error("승인한 모든 행에 키워드명·카테고리·리스크 등급·심의기준·증빙자료 유형을 입력하세요.")
        else:
            approved_pairs = [(_ocr_normalize(r.term), _ocr_normalize(r.category)) for r in approved.itertuples()]
            duplicate_pairs = len(approved_pairs) != len(set(approved_pairs)) or any(pair in existing_pairs for pair in approved_pairs)
            if duplicate_pairs:
                st.error("승인 후보에 기존 DB 또는 후보끼리 중복된 키워드가 있습니다. 중복을 수정하거나 승인 해제하세요.")
            else:
                rows = []
                working_df = base_df.copy()
                try:
                    for row in approved.to_dict("records"):
                        st.session_state.kw_df = working_df
                        kwd_no = next_kwd_no(row["category"])
                        values = [kwd_no, row["term"], row["category"], row["risk"], row["alternative"], row["detail"], row["evidence"], "0", ""]
                        new_row = dict(zip(DB_COLS, values))
                        rows.append(new_row)
                        working_df = pd.concat([working_df, pd.DataFrame([new_row])], ignore_index=True)
                finally:
                    st.session_state.kw_df = base_df
                incoming = pd.DataFrame(rows, columns=DB_COLS)
                merged, _, _ = merge_or_overwrite(base_df, incoming, "merge")
                st.session_state.kw_df = merged
                save_db(merged, Path(st.session_state.storage_path), allow_ocr_member=True)
                st.session_state.ocr_keyword_candidates = []
                st.session_state.ocr_keyword_editor_version = version + 1
                st.session_state[image_version_key] = int(st.session_state.get(image_version_key, 0)) + 1
                st.session_state[stored_uploads_key] = []
                st.session_state.pop('ocr_keyword_collection_id', None)
                st.success(f"관리자 승인 키워드 {len(rows)}건을 등록했습니다.")
                st.rerun()


def render_regulation_chat_tab():
    st.subheader("심의 Chat-bot")
    st.caption("기존 분석과 별도로, 질문을 보냈을 때만 키워드 DB와 공식 법령·판례 검색을 수행합니다. 검색 결과가 법적 결론을 뜻하지는 않습니다.")
    history = st.session_state.setdefault("regulation_chat_history", [])
    for turn in history:
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            st.markdown(turn["result"].get("answer", "검색 결과가 없습니다."))
            if turn["result"].get("administrator_review"):
                st.warning("검색 근거가 상충하거나 설명을 검증하지 못했습니다. 세부 판단은 관리자에게 문의해 주세요.")
            matches = turn["result"].get("keyword_matches", [])
            if matches:
                _selectable_dataframe(pd.DataFrame(matches), hide_index=True, width="stretch", alt="법령 조문에서 확인한 키워드 DB 결과")
            for source in turn["result"].get("sources", []):
                with st.expander(f"근거: {source['label']}"):
                    if source.get("url"):
                        st.link_button("원문/API 응답 열기", source["url"])
                    st.text(source.get("text", ""))

    ocr_candidates = [str(row.get("term", "")).strip()
                      for row in st.session_state.get("ocr_keyword_candidates", [])
                      if str(row.get("term", "")).strip()]
    with st.form("regulation_chat_form", clear_on_submit=True):
        direction_label = st.selectbox(
            "질문 방향",
            ["광고 문구·키워드에서 법령 찾기", "법령·조항에서 등록 키워드 찾기"],
            key="regulation_chat_direction",
        )
        question = st.text_input(
            "질문 또는 검색어",
            max_chars=500,
            placeholder="예: 화장품 광고의 주름 개선 표현 관련 조항 / 화장품법 제13조에서 등록 키워드 찾기",
        )
        selected_ocr = st.multiselect(
            "현재 OCR 후보 연결 (선택)", sorted(set(ocr_candidates)),
            key="regulation_chat_ocr_context",
        ) if ocr_candidates else []
        include_analysis_text = st.checkbox(
            "현재 텍스트 분석 문구도 검색에 포함", value=False,
            key="regulation_chat_include_analysis_text",
        )
        category_options = [""]
        if "상품카테고리" in st.session_state.kw_df:
            category_options += sorted({str(value).strip() for value in
                                        st.session_state.kw_df["상품카테고리"].dropna()
                                        if str(value).strip()})
        category = st.selectbox("상품 분류", category_options,
                                format_func=lambda value: value or "모든 분류",
                                key="regulation_chat_category")
        submitted = st.form_submit_button("검색하고 답변 보기", type="primary")

    clear_col, _ = st.columns([1, 5])
    if clear_col.button("대화 지우기", key="clear_regulation_chat"):
        st.session_state["regulation_chat_history"] = []
        st.rerun()

    if not submitted:
        return
    if not question.strip():
        st.warning("질문이나 검색어를 입력해 주세요.")
        return

    context_parts = list(selected_ocr)
    if include_analysis_text:
        context_parts.append(str(st.session_state.get("analysis_input_text", "")))
    session = st.session_state.get("auth_session") or {}
    access_token = session.get("access_token", "")
    api_url = os.getenv("REGULATION_API_URL", "").strip()
    if not api_url:
        try:
            api_url = str(st.secrets.get("REGULATION_API_URL", "")).strip()
        except Exception:
            api_url = ""
    api_url = api_url.rstrip("/")
    if not api_url or not access_token:
        st.session_state["regulation_chat_history"].append({
            "question": question,
            "result": {"answer": "법령 검색 API 주소 또는 로그인 토큰이 설정되지 않았습니다. 운영자 설정을 확인해 주세요.",
                       "sources": [], "keyword_matches": []},
        })
        st.rerun()

    direction = "keyword_to_law" if direction_label.startswith("광고") else "law_to_keywords"
    try:
        response = requests.post(
            f"{api_url}/api/v1/regulation/questions",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"direction": direction, "query": question.strip(),
                  "context_text": "\n".join(context_parts), "category": category},
            timeout=90,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "법령 검색을 완료하지 못했습니다.")
            except ValueError:
                detail = "법령 검색을 완료하지 못했습니다."
            result = {"answer": str(detail)[:500], "sources": [], "keyword_matches": []}
        else:
            result = response.json()
    except requests.RequestException:
        result = {"answer": "법령 검색 API에 연결할 수 없습니다. 기존 키워드/OCR 분석은 계속 사용할 수 있습니다.",
                  "sources": [], "keyword_matches": []}
    st.session_state["regulation_chat_history"].append({"question": question, "result": result})
    st.rerun()


show_user_management = cloud_enabled() and is_admin()
tab_specs = [('analysis', '스크립트 분석')]
if is_admin() or (
    cloud_enabled()
    and ((st.session_state.get('cloud_user') or {}).get('app_metadata') or {}).get('role') == 'member'
):
    tab_specs.append(('ocr_import', '이미지 OCR분석'))
tab_specs.append(('candidate_pool', '미매칭 후보군'))
if cloud_enabled():
    tab_specs.append(('requests', '키워드 문의내역'))
if cloud_enabled():
    tab_specs.append(('regulation_chat', '심의 Chat-bot'))
tab_specs.append(('report', '분석리포트'))
if is_admin():
    tab_specs.append(('keyword_admin', '키워드 관리'))
if show_user_management:
    tab_specs.append(('user_admin', '사용자 관리'))

tabs = dict(zip(
    (key for key, _ in tab_specs),
    st.tabs([label for _, label in tab_specs], on_change="rerun", key="main_app_tabs"),
))

if st.session_state.get('unmatched_pending_collections'):
    st.warning('미매칭 후보 중 아직 DB에 저장하지 못한 분석이 있습니다. 저장 전에는 로그아웃하지 마세요.')
    if st.button('수집 저장 재시도', key='retry_unmatched_collection'):
        _flush_unmatched_collections()
        st.rerun()
with tabs['analysis']:
    # ① 텍스트 입력
    st.subheader("텍스트 입력")
    sample = "\uc774 \ubb38\uc7a5\uc5d0\ub294 \ud544\ub7ec\uc640 \uc548\ud2f0\uc5d0\uc774\uc9d5\uc774\ub77c\ub294 \ud0a4\uc6cc\ub4dc\uac00 \ud3ec\ud568\ub418\uc5b4 \uc788\uc2b5\ub2c8\ub2e4."
    if "analysis_input_text" not in st.session_state:
        st.session_state.analysis_input_text = sample
    text = st.text_area("\ubd84\uc11d\ud560 \ud14d\uc2a4\ud2b8", key="analysis_input_text", height=180, max_chars=20000)

    st.markdown("---")
    # ②) 분석 실행
    st.subheader("분석 실행")
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
                format_func=matching_mode_option_label,
                on_change=invalidate_analysis_result,
            )
            if match_mode == MATCH_MODES['partial']:
                st.number_input("최소 일치 글자수", min_value=2, max_value=20,
                                value=int(st.session_state.get("partial_min_len", 2) or 2),
                                step=1, key="partial_min_len", persist_state="session",
                                on_change=invalidate_analysis_result,
                                help=_numbered_help('예시) 등록 `안티에이징` / 입력 `에이징 관리가 필요하다`\n\n- O · 최소 3글자 → `에이징` 검출\n- X · 최소 4글자 → 미검출\n\n옵션에 따라 공백·기호를 처리한 뒤의 글자수를 기준으로 합니다.\n\n등록 키워드 자체가 최소 글자수보다 짧으면 검색하지 않습니다.'))
            with st.expander('키워드 매칭 옵션', expanded=False):
                for name, (label, description) in MATCH_NORMALIZATION_OPTIONS.items():
                    st.checkbox(label, key=name, help=_numbered_help(description), on_change=invalidate_analysis_result)
                st.caption('옵션을 변경하면 이전 결과를 숨깁니다.\n\n텍스트 분석하기를 눌러 새 조건으로 검사하세요.')
                if match_mode == MATCH_MODES['exact'] and not st.session_state.strip_bracket_notes:
                    st.info('현재는 괄호까지 포함한 등록명을 찾습니다.\n\n안티에이징(anti-aging)을 안티에이징으로에서도 찾으려면 괄호 설명 제외를 켜세요.')
            rules_summary = st.empty()
            with rules_summary.container():
                render_matching_rules_summary(_matching_config())

    st.caption('미매칭 표현은 분석할 때마다 자동 수집됩니다. 원문·이미지·계정 정보는 후보 통계에 저장하지 않습니다.')
    analyze_clicked = st.button("텍스트 분석하기", type="primary", key="btn_analyze")
    auto_analyze = bool(st.session_state.pop("analysis_auto_run_pending", False))
    if analyze_clicked or auto_analyze:
        try:
            # 항상 최신 키워드 DB 상태를 반영하기 위해 저장 경로에서 다시 로드
            try:
                st.session_state.kw_df = load_db(Path(st.session_state.storage_path))
            except Exception as _e:
                st.warning(f"키워드 DB를 다시 불러오는 중 오류가 발생했습니다: {_e}")
            if st.session_state.kw_df.empty:
                _collect_unmatched_text(text, [])
                st.info("키워드가 없습니다. 먼저 추가하세요.")
            else:
                config = _matching_config()
                if cloud_enabled():
                    config = load_matching_config(SupabaseRepository(), config)
                    st.session_state.ko_suffix_whitelist_extra = sorted(config.ko_suffixes - _KO_SUFFIX_WHITELIST)
                    st.session_state.ignored_special_symbols = list(config.ignored_symbols)
                with rules_summary.container():
                    render_matching_rules_summary(config)
                approved_partials = load_approved_partials() if config.mode == 'similar' else None
                matches = match_text(
                    text, st.session_state.kw_df, config=config,
                    categories=st.session_state.get('pre_cats', []),
                    risks=st.session_state.get('pre_risks', []),
                    approved_partials=approved_partials,
                )
                analysis_id = str(uuid4())
                try:
                    coverage_matches = matches
                    if st.session_state.get('pre_cats') or st.session_state.get('pre_risks'):
                        coverage_matches = match_text(
                            text, st.session_state.kw_df, config=config,
                            approved_partials=approved_partials,
                        )
                    if _collect_unmatched_text(text, coverage_matches, analysis_id):
                        st.caption('미매칭 후보 수집을 완료했습니다.')
                except Exception as pool_error:
                    st.warning(f"미매칭 후보 집계에 실패했지만 텍스트 분석은 계속합니다: {pool_error}")
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
                        result = {'analysis_id': analysis_id,
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
                    st.session_state['analysis_highlight_html'] = highlight_text(
                        text, matches, config=config, approved_partials=approved_partials)
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
        st.success(f"총 {_persist_count}건의 키워드가 발견되었습니다.")

        # DB의 '모든 열'과 조인하여 전체 정보 표시
        try:
            merged_full = _persist_df_unique[["kwd_no"]].merge(
                st.session_state.kw_df[get_db_cols()], on="kwd_no", how="left"
            )
            merged_full = sort_for_display(merged_full)
        except Exception:
            merged_full = _persist_df_unique

        _selectable_dataframe(_rename_fcol(merged_full), width="stretch", alt="Keywords found in the latest analysis")

        if _persist_csv is not None:
            st.download_button("분석 결과 CSV 다운로드", data=_persist_csv, file_name="analysis_results.csv", mime="text/csv", key="dl_analysis")


    st.subheader(
        "하이라이트 미리보기",
        help=_numbered_help('검출 문구를 클릭하면 같은 검출 대상의 번호 표시를 전환합니다.\n\n'
             '번호 클릭은 상세 정보, Ctrl+클릭은 같은 검출 대상의 번호를 선택합니다. 선택 후 Ctrl+C로 복사할 수 있습니다.\n\n'
             '색상은 연결된 키워드의 리스크 등급을 나타냅니다.\n'
             '연분홍: 1등급(사용금지) · 하늘색: 2등급(대체키워드사용) · 연보라: 3등급(조건부사용)\n'
             '연두빛 초록: 4등급(사용가능) · 연두색: 5등급(테스트 등급)\n\n'
             '노란색은 같은 검출 문구에 서로 다른 등급의 키워드가 연결되었거나, 등급을 확인할 수 없을 때 표시됩니다.\n'
             '하나의 유효 등급만 연결된 경우 해당 등급의 색으로 표시합니다. 자세한 기준은 결과 표의 리스크 등급을 확인하세요.'),
    )
    # 기존 하이라이트 HTML은 그대로 표시
    # Inject tooltip data + click popup renderer without changing preview body text.
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
        .hl-box .hl-mark {{ cursor: pointer; }}
        .kwdno-group {{ white-space: nowrap; }}
        .kwdno-group::before {{ content: '('; }}
        .kwdno-group::after {{ content: ')'; }}
        .kwdno-entry:not([hidden]) ~ .kwdno-entry:not([hidden])::before {{ content: ', '; }}
        .kwdno-entry[hidden] {{ display: none; }}
        .kwdno-link.group-selected {{ background: #b3d4fc; outline: 1px solid #3977c3; }}
        /* floating tooltip (table-style) */
        #kwd-tt-float {{
          position: fixed;
          z-index: 2147483647;
          display: none;
          box-sizing: border-box;
          width: max-content;
          min-width: min(360px, calc(100vw - 24px));
          max-width: min(720px, calc(100vw - 24px));
          height: auto;
          max-height: calc(100vh - 16px);
          min-height: 0;
          overflow: auto;
          resize: none;
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
              if(r[0] === '매칭 결과' && r.length >= 5) {{
                function boldCore(value, core){{
                  value = String(value || '');
                  core = String(core || '');
                  var at = core ? value.indexOf(core) : -1;
                  if(at < 0) return esc(value);
                  return esc(value.slice(0, at)) + '<strong>' + esc(core) + '</strong>' + esc(value.slice(at + core.length));
                }}
                html += '<tr><th>' + esc(r[0]) + '</th><td>입력 문구 ‘' + boldCore(r[1], r[3]) +
                  '’ ↔ DB 등록 키워드 ‘' + boldCore(r[2], r[4]) + '’</td></tr>';
                continue;
              }}
              html += '<tr><th>' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td></tr>';
            }}
            html += '</tbody></table>';
            return html;
          }}

          var tt = document.getElementById('kwd-tt-float');
          var activeTarget = null;
          var hideTimer = null;
          var hoverTimer = null;
          var hiddenKeywords = new Set();
          var selectedGroupKey = null;
          var compactFrameHeight = Number('{_preview_content_height}') || 70;

          function resizePreviewFrame(height, popupOpen){
            try {
              if(!window.frameElement) return;
              window.frameElement.style.height = Math.ceil(height) + 'px';
              window.frameElement.style.position = popupOpen ? 'relative' : '';
              window.frameElement.style.zIndex = popupOpen ? '2147483646' : '';
            } catch(e) {}
          }

          function renderNumberGroup(group){{
            var entries = Array.from(group.querySelectorAll('.kwdno-entry'));
            entries.forEach(function(entry){{
              entry.hidden = hiddenKeywords.has(entry.getAttribute('data-kwd-toggle'));
            }});
            group.hidden = entries.every(function(entry){{ return entry.hidden; }});
          }}

          function toggleHighlight(target){{
            var groups = Array.from(target.querySelectorAll('.kwdno-group'));
            var codes = Array.from(new Set(groups.flatMap(function(group){{
              return Array.from(group.querySelectorAll('.kwdno-entry'))
                .map(function(entry){{ return entry.getAttribute('data-kwd-toggle'); }});
            }})));
            if(!codes.length) return;
            var turnOff = codes.some(function(code){{ return !hiddenKeywords.has(code); }});
            codes.forEach(function(code){{
              if(turnOff) hiddenKeywords.add(code);
              else hiddenKeywords.delete(code);
            }});
            document.querySelectorAll('.kwdno-group').forEach(renderNumberGroup);
          }}

          function selectKeywordNumbers(target){{
            var groupKey = target.getAttribute('data-group-key');
            if(!groupKey) return;
            hide(true);
            selectedGroupKey = groupKey;
            document.querySelectorAll('.kwdno-link').forEach(function(link){{
              link.classList.toggle('group-selected', link.getAttribute('data-group-key') === groupKey);
            }});
          }}

          function clearKeywordNumberSelection(){{
            selectedGroupKey = null;
            document.querySelectorAll('.kwdno-link.group-selected').forEach(function(link){{
              link.classList.remove('group-selected');
            }});
          }}

          function hide(immediate){{
            if(hideTimer) clearTimeout(hideTimer);
            if(hoverTimer) clearTimeout(hoverTimer);
            hoverTimer = null;
            function close(){{
              tt.style.display = 'none';
              tt.setAttribute('aria-hidden', 'true');
              if(activeTarget) activeTarget.setAttribute('aria-expanded', 'false');
              activeTarget = null;
              hideTimer = null;
              resizePreviewFrame(compactFrameHeight, false);
            }}
            if(immediate) close();
            else hideTimer = setTimeout(close, 180);
          }}

          function showFor(target, toggle){{
            if(!target) return;
            var kwd = target.getAttribute('data-kwd');
            if(!kwd) return;

            if(hideTimer) clearTimeout(hideTimer);
            if(activeTarget === target) {{
              if(toggle) hide(true);
              return;
            }}
            hide(true);
            activeTarget = target;
            target.setAttribute('aria-expanded', 'true');
            tt.style.height = '';
            tt.style.minHeight = '';

            var data = getData();
            var tooltipKey = target.getAttribute('data-tooltip-key');
            var rows = data[tooltipKey] || data[kwd];
            if(!rows || !rows.length) {{
              rows = [['kwd_no', kwd], ['msg', 'tooltip 데이터가 없습니다.']];
            }}
            tt.innerHTML = buildTable(rows);

            tt.style.display = 'block';
            tt.setAttribute('aria-hidden', 'false');
            // Expand the iframe only while the floating detail popup is open.
            // This gives the popup its own viewport without leaving a large
            // empty gap below a short preview after the popup closes.
            resizePreviewFrame(Math.min(540, Math.max(compactFrameHeight, tt.scrollHeight + 32)), true);
            void document.documentElement.offsetHeight;

            // Treat the whole number group as the protected anchor, not only the hovered code.
            var row = target.closest('.kwdno-group') || target;
            var rect = row.getBoundingClientRect();

            // keep inside viewport
            var bw = tt.offsetWidth;
            var bh = tt.offsetHeight;
            var vw = window.innerWidth;
            var vh = window.innerHeight;

            var gap = 12;
            var margin = 8;
            function findBestPosition(width, height){
              var maxX = Math.max(margin, vw - width - margin);
              var maxY = Math.max(margin, vh - height - margin);
              var candidates = [
                [rect.left, rect.bottom + gap],
                [rect.right - width, rect.bottom + gap],
                [rect.left, rect.top - height - gap],
                [rect.right - width, rect.top - height - gap],
                [rect.right + gap, rect.top],
                [rect.left - width - gap, rect.top],
                [rect.right + gap, rect.bottom - height],
                [rect.left - width - gap, rect.bottom - height]
              ];
              var best = null;
              candidates.forEach(function(pos, index){
                var x = Math.max(margin, Math.min(pos[0], maxX));
                var y = Math.max(margin, Math.min(pos[1], maxY));
                var overlapW = Math.max(0, Math.min(x + width, rect.right) - Math.max(x, rect.left));
                var overlapH = Math.max(0, Math.min(y + height, rect.bottom) - Math.max(y, rect.top));
                var overlapArea = overlapW * overlapH;
                var score = overlapArea * 1000000 + index;
                if(!best || score < best.score) best = {x:x, y:y, score:score, overlapArea:overlapArea};
              });
              return best;
            }
            var best = findBestPosition(bw, bh);
            if(best.overlapArea > 0){
              var roomBelow = vh - margin - rect.bottom - gap;
              var roomAbove = rect.top - gap - margin;
              var verticalRoom = Math.max(roomBelow, roomAbove);
              if(verticalRoom > 0 && verticalRoom < bh){
                tt.style.minHeight = '0px';
                tt.style.height = Math.floor(verticalRoom) + 'px';
                bw = tt.offsetWidth;
                bh = tt.offsetHeight;
                best = findBestPosition(bw, bh);
              }
            }
            var x = best.x;
            var y = best.y;
            tt.style.left = x + 'px';
            tt.style.top  = y + 'px';
          }}

          function bind(){{
            var box = document.querySelector('.hl-box');
            if(!box) return false;
            if(!box.__kwd_selection_clear_bound){{
              box.__kwd_selection_clear_bound = true;
              box.addEventListener('click', function(ev){{
                var target = ev.target && ev.target.nodeType === 1 ? ev.target : ev.target.parentElement;
                if(target && (target.closest('.kwdno-link') || target.closest('.hl-mark'))) return;
                clearKeywordNumberSelection();
              }});
            }}
            box.querySelectorAll('.hl-mark').forEach(function(mark){{
              if(mark.__kwd_toggle_bound) return;
              mark.__kwd_toggle_bound = true;
              mark.addEventListener('click', function(ev){{
                if(ev.target.closest('.kwdno-link')) return;
                toggleHighlight(mark);
              }});
              mark.addEventListener('keydown', function(ev){{
                if((ev.key === 'Enter' || ev.key === ' ') && !ev.target.closest('.kwdno-link')) {{
                  ev.preventDefault();
                  toggleHighlight(mark);
                }}
              }});
            }});
            var els = box.querySelectorAll('[data-kwd]');
            if(!els || !els.length) return false;

            for(var i=0;i<els.length;i++) {{
              var el = els[i];
              if(el.__kwd_tt_bound) continue;
              el.__kwd_tt_bound = true;

              el.setAttribute('role', 'button');
              el.setAttribute('tabindex', '0');
              el.setAttribute('aria-controls', 'kwd-tt-float');
              el.setAttribute('aria-expanded', 'false');
              el.setAttribute('aria-label', el.getAttribute('data-kwd') + ' 상세 정보');
              el.addEventListener('mouseenter', function(ev){{
                var target = ev.currentTarget;
                if(hoverTimer) clearTimeout(hoverTimer);
                hoverTimer = setTimeout(function(){{
                  hoverTimer = null;
                  showFor(target, false);
                }}, 500);
              }});
              el.addEventListener('mouseleave', function(){{
                if(hoverTimer) clearTimeout(hoverTimer);
                hoverTimer = null;
                hide(false);
              }});
              el.addEventListener('click', function(ev){{
                if(ev.ctrlKey || ev.metaKey) {{
                  ev.preventDefault();
                  selectKeywordNumbers(ev.currentTarget);
                }} else showFor(ev.currentTarget, true);
              }});
              el.addEventListener('keydown', function(ev){{
                if(ev.key === 'Enter' || ev.key === ' ') {{
                  ev.preventDefault();
                  showFor(ev.currentTarget);
                }}
              }});
            }}

            if(!tt.__kwd_hover_bound) {{
              tt.__kwd_hover_bound = true;
              tt.addEventListener('mouseenter', function(){{
                if(hideTimer) clearTimeout(hideTimer);
                hideTimer = null;
              }});
              tt.addEventListener('mouseleave', function(){{ hide(false); }});
            }}

            document.addEventListener('click', function(ev){{
              if(!tt.contains(ev.target) && !(activeTarget && activeTarget.contains(ev.target))) hide();
            }});
            document.addEventListener('keydown', function(ev){{
              if(ev.key === 'Escape') {{
                clearKeywordNumberSelection();
                var target = activeTarget;
                hide();
                if(target) target.focus();
              }}
            }});
            document.addEventListener('copy', function(ev){{
              if(!selectedGroupKey || !ev.clipboardData) return;
              var labels = Array.from(document.querySelectorAll('.kwdno-link.group-selected'))
                .map(function(link){{ return link.getAttribute('data-copy-label'); }});
              if(!labels.length) return;
              ev.clipboardData.setData('text/plain', Array.from(new Set(labels)).join(', '));
              ev.preventDefault();
            }});
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
    if _persist_highlight_html:
        preview_text = html.unescape(re.sub(r'<[^>]+>', '', _persist_highlight_html))
        preview_lines = sum(
            max(1, (len(line) + 51) // 52)
            for line in (preview_text.splitlines() or [preview_text])
        )
        preview_content_height = min(540, max(70, 38 + preview_lines * 26))
    else:
        preview_content_height = 70
    _component_html = _component_html.replace('{_preview_content_height}', str(preview_content_height))
    _component_html = _component_html.replace('{{', '{').replace('}}', '}')

    # Keep the document flow proportional to preview content. The frame expands
    # temporarily in JavaScript while its floating detail popup is visible.
    if _persist_highlight_html:
        components.html(_component_html, height=preview_content_height, scrolling=True)


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
    st.caption(f"\ud604\uc7ac \ud45c\uc2dc\ub41c \ud56d\ubaa9: {len(_filtered_df)} / \uc804\uccb4: {len(_base_df)}")
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
        _cfg[LAST_HIT_COL] = cc.TextColumn(label=LAST_SEARCH_LABEL)

        _kwd_col_config = _cfg
    except Exception:
        _kwd_col_config = None

    try:
        _selectable_dataframe(_rename_fcol(_list_view_df), width="stretch", column_config=_kwd_col_config or {}, alt="Keyword database list")
    except TypeError:
        _selectable_dataframe(_rename_fcol(_list_view_df), width="stretch", alt="Keyword database list")

    buf_bytes = io.BytesIO()
    st.session_state.kw_df[get_db_cols()].rename(columns={LAST_HIT_COL: LAST_SEARCH_LABEL}).to_csv(
        buf_bytes, index=False, encoding="utf-8-sig"
    )
    st.download_button("키워드 CSV 다운로드", data=buf_bytes.getvalue(), file_name="keywords_current.csv", mime="text/csv", key="dl_kw_current")

if cloud_enabled():
    with tabs['requests']:
        # Streamlit runs every tab body on normal reruns. Keep a stale
        # selection in the requests table from reopening its dialog while
        # the user is working in another tab.
        if tabs['requests'].open:
            render_keyword_requests_tab()

def build_unmatched_registration_candidates(selected):
    required = ['term', '상품카테고리', '리스크 등급',
                '리스크 등급별 세부 심의기준', '증빙자료유형']
    if selected.empty:
        raise ValueError("정규화 후보를 선택하세요.")
    if selected[required].fillna('').astype(str).apply(lambda col: col.str.strip().eq('')).any().any():
        raise ValueError("선택 후보의 키워드명, 카테고리, 리스크 등급, 심의기준, 증빙자료유형을 모두 입력하세요.")
    candidates = []
    for _, item in selected.iterrows():
        term = str(item['term']).strip()
        source_terms = str(item.get('source_terms') or '').strip()
        if not 1 <= len(term) <= 150 or len(source_terms) > 500:
            raise ValueError("후보 키워드 또는 원본 표현 길이를 확인하세요.")
        occurrences = int(item.get('occurrences') or 0)
        candidates.append({
            'term': term, 'source_terms': source_terms, 'occurrences': occurrences,
            'category': str(item['상품카테고리']).strip(),
            'risk': str(item['리스크 등급']).strip(),
            'criteria': str(item['리스크 등급별 세부 심의기준']).strip(),
            'evidence_type': str(item['증빙자료유형']).strip(),
            'alternative': str(item.get('대체키워드', '-') or '-').strip(),
        })
    return candidates


def unmatched_registration_source_keys(selected):
    keys = set()
    for _, item in selected.iterrows():
        raw_key = item.get('term_norm', '')
        request_key = '' if pd.isna(raw_key) else str(raw_key).strip()
        if request_key:
            keys.add(request_key)
            continue
        raw_sources = item.get('source_terms', '')
        source_terms = '' if pd.isna(raw_sources) else str(raw_sources).strip()
        sources = source_terms.split(' | ') if source_terms else [str(item.get('term') or '')]
        keys.update(
            unicodedata.normalize('NFKC', source).casefold().strip()
            for source in sources if str(source).strip()
        )
    return sorted(key for key in keys if 1 <= len(key) <= 100)


def clear_registered_unmatched_candidates(selected, access_token):
    repository = SupabaseRepository()
    term_keys = unmatched_registration_source_keys(selected)
    if term_keys:
        repository.delete_unmatched_terms(term_keys, access_token)
    request_ids = [str(value) for value in selected.get('request_id', []) if str(value).strip()]
    return repository.delete_unmatched_registration_requests(request_ids, access_token) if request_ids else 0


def unmatched_recommendation_id(row):
    request_id = str(row.get('request_id') or '').strip()
    if request_id:
        return f'request:{request_id}'
    identity = '\0'.join(str(row.get(key) or '').strip()
                          for key in ('term', 'source_terms', 'occurrences'))
    return 'local:' + hashlib.sha256(identity.encode()).hexdigest()


def render_unmatched_candidate_pool():
    st.subheader("미매칭 후보군 분석 및 검토")
    if cloud_enabled():
        st.caption('모든 승인 계정의 공용 누적 통계입니다. 로그아웃 후에도 유지됩니다. OCR은 신뢰도 60% 이상만 수집합니다.')
        search = st.text_input('미매칭 표현 검색', key='unmatched_search', max_chars=100).strip()
        if search != st.session_state.get('unmatched_last_search', ''):
            st.session_state['unmatched_page'] = 0
            st.session_state['unmatched_last_search'] = search
        page = int(st.session_state.get('unmatched_page', 0))
        try:
            snapshot = SupabaseRepository().load_unmatched_terms(page * 100, 100, search)
        except Exception as exc:
            logging.exception('Could not load shared unmatched candidates')
            st.error('공용 미매칭 후보를 불러오지 못했습니다. 잠시 후 새로고침하세요.')
            st.caption(f'진단 정보: {type(exc).__name__}: {str(exc)[:200]}')
            return
        rows, total = snapshot['rows'], int(snapshot['total'])
        if page and not rows:
            st.session_state['unmatched_page'] = 0
            st.rerun()
        surface_rows = [{'surface_key': row['term_norm'], 'surface': row['display_term'],
                         'occurrences': row['total_occurrences'],
                         'analysis_count': row.get('analysis_count', 0),
                         'first_seen': row.get('first_seen'),
                         'status': {'registration_requested': '신규키워드 등록요청',
                                    'ignored': '관리자 거절'}.get(row.get('review_status'), '')}
                        for row in rows]
        st.caption(f'검색 결과 {total:,}종 · {page + 1}/{max(1, (total + 99) // 100)} 페이지')
        previous, following, refresh = st.columns(3)
        if previous.button('이전', key='unmatched_previous', disabled=page == 0):
            st.session_state['unmatched_page'] = page - 1
            st.rerun()
        if following.button('다음', key='unmatched_next', disabled=(page + 1) * 100 >= total):
            st.session_state['unmatched_page'] = page + 1
            st.rerun()
        refresh.button('목록 새로고침', key='unmatched_refresh')
        if st.button('전체 누적 CSV 만들기', key='make_unmatched_export'):
            try:
                exported = SupabaseRepository().export_unmatched_terms()
                export_frame = pd.DataFrame(exported).rename(columns={
                    'display_term': '미매칭 표현', 'total_occurrences': '누적 출현 횟수',
                    'analysis_count': '분석 횟수', 'review_status': '상태',
                    'first_seen': '최초 수집 시각', 'last_seen': '최근 수집 시각',
                }).drop(columns=['term_norm'], errors='ignore')
                if '상태' in export_frame:
                    export_frame['상태'] = export_frame['상태'].replace({
                        'registration_requested': '신규키워드 등록요청',
                        'ignored': '관리자 거절',
                    })
                for column in ('최초 수집 시각', '최근 수집 시각'):
                    if column in export_frame:
                        export_frame[column] = pd.to_datetime(export_frame[column], utc=True).dt.tz_convert('Asia/Seoul')
                st.session_state['unmatched_export_csv'] = export_frame.to_csv(index=False).encode('utf-8-sig')
            except Exception:
                st.error('전체 CSV를 만들지 못했습니다. 다시 시도하세요.')
        if st.session_state.get('unmatched_export_csv'):
            st.download_button('전체 누적 CSV 다운로드', st.session_state['unmatched_export_csv'],
                               'unmatched_candidates.csv', 'text/csv', key='download_unmatched_surfaces')
    else:
        st.caption('로컬 CSV 개발 모드: 공용 영구 누적은 Supabase 서버 모드에서 사용하세요.')
        surface_rows = list(st.session_state.get('unmatched_candidate_pool', {}).values())
        surface_rows.sort(key=lambda row: (-int(row.get('occurrences', 0) or 0), row.get('surface_key', '')))
        if surface_rows:
            st.download_button('로컬 후보 CSV 다운로드',
                pd.DataFrame(surface_rows).to_csv(index=False).encode('utf-8-sig'),
                'unmatched_candidates.csv', 'text/csv', key='download_unmatched_surfaces')
    review = st.session_state.setdefault('unmatched_candidate_review', {'edits': {}, 'deleted': []})
    review_revision = int(st.session_state.get('unmatched_candidate_review_revision', 0))
    review_rows = [
        {**row, 'surface': review['edits'].get(row['surface_key'], row.get('surface', ''))}
        for row in surface_rows if row['surface_key'] not in review['deleted']
    ]
    if review_rows:
        candidate_df = pd.DataFrame([
            {'미매칭 표현': row['surface'],
             '\uB4F1\uB85D\uC77C\uC2DC': pd.to_datetime(row.get('first_seen'), utc=True).tz_convert('Asia/Seoul')
                          if row.get('first_seen') else pd.NaT,
             '처리상태': row.get('status', ''),
             '검출횟수(중복포함)': int(row.get('occurrences', 0) or 0),
             **({'분석 횟수': int(row.get('analysis_count', 0) or 0)} if cloud_enabled() else {})}
            for row in review_rows
        ])
        selection = _selectable_dataframe(
            candidate_df, hide_index=True, width='stretch',
            alt='Shared unmatched-expression review list',
            column_config={
                '미매칭 표현': st.column_config.TextColumn('미매칭 표현'),
                '\uB4F1\uB85D\uC77C\uC2DC': st.column_config.DatetimeColumn('\uB4F1\uB85D\uC77C\uC2DC', format='YYYY-MM-DD HH:mm'),
                '처리상태': st.column_config.TextColumn('처리상태'),
                '검출횟수(중복포함)': st.column_config.NumberColumn('검출횟수(중복포함)'),
                **({'분석 횟수': st.column_config.NumberColumn('분석 횟수')} if cloud_enabled() else {}),
            },
            on_select='rerun', selection_mode='multi-row',
            key=f"unmatched_candidate_selector_{page if cloud_enabled() else 'local'}_{st.session_state.get('unmatched_search', '')}_{review_revision}",
        )
        selected_positions = selection.selection.rows
        selected_rows = [review_rows[index] for index in selected_positions if 0 <= index < len(review_rows)]
        selected_ids = [row['surface_key'] for row in selected_rows]
        st.caption('표에서 행을 선택해 선택 항목만 분석할 수 있습니다. 한 행을 선택하면 표현을 수정할 수 있습니다. 관리자는 선택한 공용 후보를 영구 삭제할 수 있습니다.')
        if len(selected_rows) == 1:
            selected_row = selected_rows[0]
            with st.form(f"unmatched_candidate_edit_{selected_row['surface_key']}"):
                edited_surface = st.text_input('선택 후보 표현 수정', value=selected_row['surface'])
                if st.form_submit_button('표현 수정 저장'):
                    if not edited_surface.strip():
                        st.warning('미매칭 표현을 입력하세요.')
                    else:
                        review['edits'][selected_row['surface_key']] = edited_surface.strip()
                        st.success('선택한 표현을 수정했습니다.')
        if cloud_enabled() and is_admin():
            confirm_selected_delete = st.checkbox(
                '현재 누적 통계와 관측 기록을 삭제합니다. 이후 새 분석에서는 다시 수집될 수 있습니다.',
                key='confirm_selected_unmatched_delete')
            if st.button('선택 표현 영구 삭제', key='delete_selected_unmatched_review_rows',
                         disabled=not selected_ids or not confirm_selected_delete):
                try:
                    SupabaseRepository().delete_unmatched_terms(
                        selected_ids, st.session_state['auth_session']['access_token'])
                    _clear_unmatched_review()
                    st.session_state['unmatched_page'] = 0
                    st.session_state.pop('confirm_selected_unmatched_delete', None)
                    st.rerun()
                except (StorageError, PermissionError):
                    st.error('영구 삭제에 실패했습니다. 관리자 권한과 연결 상태를 확인하세요.')
        elif st.button('선택 행 숨기기 (현재 화면)', key='delete_selected_unmatched_review_rows',
                       disabled=not selected_ids):
            review['deleted'].extend(identity for identity in selected_ids if identity not in review['deleted'])
            for identity in selected_ids:
                review['edits'].pop(identity, None)
            st.session_state['unmatched_candidate_review_revision'] = review_revision + 1
            st.rerun()
        if st.button("선택후보군 정규화 작업", type="primary", key="analyze_unmatched_candidate_pool"):
            if not selected_rows:
                st.warning('분석할 행을 표에서 선택하세요.')
            else:
                try:
                    normalize_candidates = _get_auxiliary_analysis_function(
                        "normalize_unmatched_term_candidates"
                    )
                    analysis_rows = [
                        {'surface': row['surface'],
                         'occurrences': int(row.get('occurrences', 0) or 0)}
                        for row in selected_rows
                    ]
                    recommendations = normalize_candidates(analysis_rows)
                    st.session_state["unmatched_candidate_recommendations"] = recommendations
                    st.session_state['unmatched_recommendation_hidden_ids'] = []
                    st.session_state['unmatched_recommendation_selected_ids'] = []
                    st.session_state['unmatched_recommendation_edits'] = {}
                    st.session_state["unmatched_recommendation_version"] = int(
                        st.session_state.get("unmatched_recommendation_version", 0)
                    ) + 1
                    st.success(f"정규화 추천 {len(recommendations)}건을 만들었습니다. 검토 후 승인하세요.")
                except Exception as pool_error:
                    st.error(f"미매칭 후보군 분석에 실패했습니다: {pool_error}")
    elif surface_rows:
        st.info('현재 검토 목록에서 모두 제외된 상태입니다. 검토 입력 초기화로 다시 불러올 수 있습니다.')
        if st.button("검토 입력 초기화", key="clear_unmatched_candidate_pool"):
            _clear_unmatched_review()
            st.rerun()
    else:
        st.info("아직 후보가 없습니다. 텍스트 분석 또는 한국어 OCR을 실행하면 자동으로 수집됩니다.")

    recommendations = list(st.session_state.get("unmatched_candidate_recommendations", []))
    registration_requests = []
    if cloud_enabled() and is_admin():
        try:
            registration_requests = SupabaseRepository().load_unmatched_registration_requests(
                st.session_state.auth_session['access_token']
            )
        except (StorageError, PermissionError) as exc:
            st.error(f"\ub4f1\ub85d \uc694\uccad\uc744 \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4: {exc}")
        else:
            recommendations = [
                {'term': row['term'], 'source_terms': row.get('source_terms', ''),
                 'occurrences': row.get('occurrences', 0), 'request_id': row['id'],
                 'term_norm': row.get('term_norm', ''),
                 'request_date': row.get('created_at', ''),
                 '상품카테고리': row.get('category', ''),
                 '리스크 등급': row.get('risk', ''),
                 '리스크 등급별 세부 심의기준': row.get('criteria', ''),
                 '증빙자료유형': row.get('evidence_type', ''),
                 '대체키워드': row.get('alternative', '-')}
                for row in registration_requests
            ] + recommendations
            if registration_requests:
                st.caption(f"\ub204\uc801\ub41c DB \ub4f1\ub85d \uc694\uccad: {len(registration_requests)}\uac74")
    recommendations = [
        {**row, 'recommendation_id': unmatched_recommendation_id(row)}
        for row in recommendations
    ]
    hidden_recommendation_ids = set(
        st.session_state.get('unmatched_recommendation_hidden_ids', []))
    recommendations = [row for row in recommendations
                       if row['recommendation_id'] not in hidden_recommendation_ids]
    if recommendations:
        st.markdown("#### 정규화 추천 및 분류 입력")
        recommendation_df = pd.DataFrame(recommendations)
        select_column = "\uC120\uD0DD"
        recommendation_df.insert(0, select_column, False)
        for column, default in {
                "\uC0C1\uD488\uCE74\uD14C\uACE0\uB9AC": "", "\uB9AC\uC2A4\uD06C \uB4F1\uAE09": "",
                "\uB9AC\uC2A4\uD06C \uB4F1\uAE09\uBCC4 \uC138\uBD80 \uC2EC\uC758\uAE30\uC900": "",
                "\uC99D\uBE59\uC790\uB8CC\uC720\uD615": "", "\uB300\uCCB4\uD0A4\uC6CC\uB4DC": "-",
                "request_id": "", "request_date": "", "term_norm": ""}.items():
            if column not in recommendation_df:
                recommendation_df[column] = default
        recommendation_ids = [row['recommendation_id'] for row in recommendations]
        saved_edits = st.session_state.get('unmatched_recommendation_edits', {})
        for index, recommendation_id in enumerate(recommendation_ids):
            for column, value in saved_edits.get(recommendation_id, {}).items():
                if column in recommendation_df.columns:
                    recommendation_df.at[index, column] = value
        selected_ids = set(st.session_state.get('unmatched_recommendation_selected_ids', []))
        recommendation_df[select_column] = [
            recommendation_id in selected_ids for recommendation_id in recommendation_ids
        ]
        recommendation_df = recommendation_df[
            [select_column] + [column for column in recommendation_df.columns if column != select_column]
        ]
        ids_hash = hashlib.sha256(','.join(recommendation_ids).encode()).hexdigest()[:12]
        editor_key = (f"unmatched_recommendation_editor_{st.session_state.get('unmatched_recommendation_version', 0)}_"
                      + ids_hash)
        select_all_key = f"unmatched_recommendation_select_all_{ids_hash}"
        st.session_state.setdefault(
            select_all_key,
            bool(recommendation_ids) and all(item in selected_ids for item in recommendation_ids),
        )
        st.checkbox(
            "\uC120\uD0DD",
            key=select_all_key,
            on_change=_set_unmatched_select_all,
            args=(recommendation_ids, select_all_key),
            help="\uB204\uB974\uBA74 \uD45C\uC758 \uD56D\uBAA9\uC744 \uBAA8\uB450 \uC120\uD0DD\uD558\uAC70\uB098 \uD574\uC81C\uD569\uB2C8\uB2E4.",
            label_visibility="collapsed",
        )
        edited_recommendations = st.data_editor(
            recommendation_df,
            alt="Unmatched keyword normalization recommendations",
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            on_change=_persist_unmatched_editor,
            args=(editor_key, recommendations, select_column, select_all_key),
            column_config={
                "선택": st.column_config.CheckboxColumn("선택"),
                "term": st.column_config.TextColumn("추천 키워드", required=True),
                "source_terms": st.column_config.TextColumn("원본 표현"),
                "occurrences": st.column_config.NumberColumn("출현 횟수", disabled=True),
                "상품카테고리": st.column_config.SelectboxColumn("상품카테고리", options=[""] + list(st.session_state.opt_categories), required=True),
                "리스크 등급": st.column_config.SelectboxColumn("리스크 등급", options=[""] + list(st.session_state.opt_risks), required=True),
                "리스크 등급별 세부 심의기준": st.column_config.SelectboxColumn("세부 심의기준", options=[""] + list(st.session_state.opt_details), required=True),
                "증빙자료유형": st.column_config.SelectboxColumn("증빙자료유형", options=[""] + list(st.session_state.opt_evidences), required=True),
                "대체키워드": st.column_config.SelectboxColumn("대체키워드", options=list(st.session_state.opt_alt_terms), required=False),
                "request_date": st.column_config.TextColumn("요청 접수일", disabled=True),
                "request_id": None,
                "term_norm": None,
                "recommendation_id": None,
            },
            key=editor_key,
        )
        if st.button('선택 항목 현재 목록에서 제외', key='exclude_unmatched_recommendations'):
            selected_for_exclusion = edited_recommendations[
                edited_recommendations['선택'].fillna(False)]
            if selected_for_exclusion.empty:
                st.warning('목록에서 제외할 항목을 선택하세요.')
            else:
                hidden = list(st.session_state.get('unmatched_recommendation_hidden_ids', []))
                hidden.extend(selected_for_exclusion['recommendation_id'].astype(str).tolist())
                st.session_state['unmatched_recommendation_hidden_ids'] = list(dict.fromkeys(hidden))
                st.rerun()
        if is_admin():
            if st.button("선택 후보 승인 및 DB 등록", type="primary", key="approve_unmatched_recommendations"):
                selected = edited_recommendations[edited_recommendations["선택"].fillna(False)].copy()
                required = ["term", "상품카테고리", "리스크 등급", "리스크 등급별 세부 심의기준", "증빙자료유형"]
                if selected.empty:
                    st.warning("먼저 등록할 후보를 선택하세요.")
                elif selected[required].fillna("").astype(str).apply(lambda col: col.str.strip().eq("")).any().any():
                    st.warning("선택한 후보의 키워드명, 카테고리, 리스크 등급, 심의기준, 증빙자료유형을 모두 입력하세요.")
                else:
                    existing_keys = {
                        (str(row.get("키워드명", "")).strip().casefold(), str(row.get("상품카테고리", "")).strip())
                        for _, row in st.session_state.kw_df.iterrows()
                    }
                    additions = []
                    for _, item in selected.iterrows():
                        term = str(item["term"]).strip()
                        category = str(item["상품카테고리"]).strip()
                        key = (term.casefold(), category)
                        if key in existing_keys:
                            continue
                        existing_keys.add(key)
                        additions.append({
                            "kwd_no": next_kwd_no(category), "키워드명": term,
                            "상품카테고리": category, "리스크 등급": str(item["리스크 등급"]).strip(),
                            "리스크 등급별 세부 심의기준": str(item["리스크 등급별 세부 심의기준"]).strip(),
                            "증빙자료유형": str(item["증빙자료유형"]).strip(),
                            "대체키워드": str(item.get("대체키워드", "-") or "-").strip(),
                            "키워드 조회 수(누적카운트)": "0", "마지막 출력일자": "", "키워드 등록일자": "",
                        })
                    if additions:
                        st.session_state.kw_df = pd.concat([st.session_state.kw_df, pd.DataFrame(additions)], ignore_index=True)
                        save_db(st.session_state.kw_df[get_db_cols()], Path(st.session_state.storage_path))
                        try:
                            cleared = clear_registered_unmatched_candidates(
                                selected, st.session_state.auth_session['access_token'])
                        except (StorageError, PermissionError, ValueError) as exc:
                            st.error(f"DB \uc800\uc7a5\uc740 \uc644\ub8cc\ud588\uc9c0\ub9cc \ubbf8\ub9e4\uce6d \ud45c\ud604\uacfc \uc694\uccad \uc815\ub9ac\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4: {exc}")
                            return
                        st.session_state["unmatched_candidate_recommendations"] = []
                        st.session_state["unmatched_recommendation_version"] = int(
                            st.session_state.get("unmatched_recommendation_version", 0)
                        ) + 1
                        st.success(f"승인된 키워드 {len(additions)}건을 DB에 등록하고 요청 {cleared}건을 정리했습니다.")
                        st.rerun()
                    else:
                        try:
                            cleared = clear_registered_unmatched_candidates(
                                selected, st.session_state.auth_session['access_token'])
                        except (StorageError, PermissionError, ValueError) as exc:
                            st.error(f"\ubbf8\ub9e4\uce6d \ud45c\ud604\uacfc \uc694\uccad \uc815\ub9ac\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4: {exc}")
                            return
                        if cleared or unmatched_registration_source_keys(selected):
                            st.success(f"\uc774\ubbf8 \ub4f1\ub85d\ub41c \ud6c4\ubcf4\uc758 \ubbf8\ub9e4\uce6d \ud1b5\uacc4\uc640 \uc694\uccad {cleared}\uac74\uc744 \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4.")
                            st.rerun()
                        st.info("선택 후보는 이미 같은 카테고리에 등록되어 있습니다.")
            if st.button('선택 요청 거절', key='reject_unmatched_registration_requests'):
                selected = edited_recommendations[
                    edited_recommendations['선택'].fillna(False)]
                request_ids = [str(value) for value in selected.get('request_id', [])
                               if str(value).strip()]
                if not request_ids:
                    st.warning('거절할 등록 요청을 선택하세요.')
                else:
                    try:
                        rejected = SupabaseRepository().reject_unmatched_registration_requests(
                            request_ids, st.session_state.auth_session['access_token'])
                    except (StorageError, PermissionError, ValueError) as exc:
                        st.error(f'등록 요청을 거절하지 못했습니다: {exc}')
                    else:
                        hidden = list(st.session_state.get('unmatched_recommendation_hidden_ids', []))
                        hidden.extend(f'request:{request_id}' for request_id in request_ids)
                        st.session_state['unmatched_recommendation_hidden_ids'] = list(dict.fromkeys(hidden))
                        st.success(f'등록 요청 {rejected}건을 거절했습니다.')
                        st.rerun()
        else:
            if cloud_enabled():
                if st.button('\uc120\ud0dd \ud6c4\ubcf4 DB \ub4f1\ub85d\uc694\uccad', type='primary', key='request_unmatched_keyword_registration'):
                    selected = edited_recommendations[edited_recommendations['\uc120\ud0dd'].fillna(False)].copy()
                    try:
                        candidates = build_unmatched_registration_candidates(selected)
                        SupabaseRepository().submit_unmatched_registration_requests(
                            candidates, st.session_state.auth_session['access_token']
                        )
                    except (StorageError, PermissionError, KeyError, ValueError) as exc:
                        st.error('DB \ub4f1\ub85d \uc694\uccad\uc744 \uc811\uc218\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc5f0\uacb0 \uc0c1\ud0dc\ub97c \ud655\uc778\ud558\uace0 \ub2e4\uc2dc \uc2dc\ub3c4\ud558\uc138\uc694.')
                        st.caption(str(exc))
                    else:
                        hidden = list(st.session_state.get('unmatched_recommendation_hidden_ids', []))
                        hidden.extend(selected['recommendation_id'].astype(str).tolist())
                        st.session_state['unmatched_recommendation_hidden_ids'] = list(dict.fromkeys(hidden))
                        st.success('\uad00\ub9ac\uc790 \uc815\uaddc\ud654 \ucd94\ucc9c \ubc0f \ubd84\ub958 \uc785\ub825\ub780\uc5d0 \uc694\uccad\uc774 \ub204\uc801\ub418\uc5c8\uc2b5\ub2c8\ub2e4.')
                        st.rerun()
            else:
                st.info("정규화 결과는 검토할 수 있지만, DB 등록은 관리자 승인 후 진행됩니다.")

with tabs['candidate_pool']:
    if tabs['candidate_pool'].open:
        render_unmatched_candidate_pool()

if is_admin():
    with tabs['keyword_admin']:
        st.subheader("키워드 관리 (편집/삭제/템플릿/업로드)")
        with st.expander('공통 분석 규칙 — 모든 사용자에게 적용', expanded=False):
            render_common_matching_rules()

        upload_col, delete_col = st.columns([1.15, 1])
        with upload_col:
            st.markdown('<div class="kw-admin-section-title">📂 키워드 업로드 (.csv / .xlsx)</div>', unsafe_allow_html=True)
            upload_mode = st.radio("\uc5c5\ub85c\ub4dc \ubaa8\ub4dc", ["\uae30\uc874 \uc720\uc9c0 + \uc0c8\ub85c \ucd94\uac00", "\uc644\uc804 \ub36e\uc5b4\uc4f0\uae30"], horizontal=False, key="upload_mode")
            st.markdown("""
            <style>
            .kw-admin-section-title {
                font-size: 1.75rem !important;
                font-weight: 600 !important;
                line-height: 1.3 !important;
                margin: 0 0 0.5rem 0 !important;
            }
            .kw-template-widget-label,
            .st-key-uploader [data-testid="stWidgetLabel"] {
                font-size: 0.875rem !important;
                font-weight: 400 !important;
                line-height: 1.5 !important;
            }
            .st-key-uploader {
                width: 50% !important;
                max-width: 50% !important;
            }
            .st-key-uploader [data-testid="stFileUploaderDropzone"] {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                justify-content: flex-start !important;
                gap: 0.5rem !important;
                min-height: 0 !important;
                padding: 0.35rem 0.65rem !important;
            }
            .st-key-uploader [data-testid="stFileUploaderDropzoneInstructions"] {
                order: 1 !important;
                flex: 0 1 auto !important;
                white-space: nowrap !important;
                font-size: 0.72rem !important;
            }
            .st-key-uploader [data-testid="stFileUploaderDropzone"] button {
                order: 0 !important;
                width: auto !important;
                min-width: 6.5rem !important;
                max-width: none !important;
                height: 2rem !important;
                min-height: 2rem !important;
                padding: 0.25rem 0.65rem !important;
                font-size: 0.875rem !important;
                white-space: nowrap !important;
            }
            div.st-key-btn_delete_rows button {
                width: 80px !important;
                min-width: 80px !important;
                padding-left: 6px !important;
                padding-right: 6px !important;
                font-size: 0.8rem !important;
            }
            </style>
            """, unsafe_allow_html=True)
            uploaded_file = st.file_uploader("\ud0a4\uc6cc\ub4dc \ud15c\ud50c\ub9bf \uc5c5\ub85c\ub4dc", type=["csv", "xlsx"], key="uploader")
            st.markdown('<div class="kw-template-widget-label">업로드 템플릿 다운로드</div>', unsafe_allow_html=True)
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


        with delete_col:
            st.markdown('<div class="kw-admin-section-title">키워드 삭제</div>', unsafe_allow_html=True)
            del_targets = st.multiselect(
                "삭제할 항목 선택 (kwd_no 기준)",
                options=sorted(st.session_state.kw_df["kwd_no"].tolist(), key=lambda value: str(value).casefold()),
                key="del_targets"
            )
            if st.button("선택 삭제", type="secondary", key="btn_delete_rows"):
                if not del_targets:
                    st.warning("삭제할 항목을 선택하세요.")
                else:
                    st.session_state.kw_df = st.session_state.kw_df[~st.session_state.kw_df["kwd_no"].isin(del_targets)].reset_index(drop=True)
                    save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                    st.success(f"{len(del_targets)}건 삭제 완료")

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

        c1, c2, c3 = st.columns(3)
        with c1:
            term_in = st.text_input("\ud0a4\uc6cc\ub4dc\uba85 *", placeholder="\uc608: \ud544\ub7ec")
        with c2:
            db_cat_opts = unique_values_from_db("\uc0c1\ud488\uce74\ud14c\uace0\ub9ac")
            cat_choice = st.selectbox("\uc0c1\ud488\uce74\ud14c\uace0\ub9ac", _ko_sorted(db_cat_opts) + ["(\uc9c1\uc811 \uc785\ub825)"])
        with c3:
            db_risk_opts = unique_values_from_db("\ub9ac\uc2a4\ud06c \ub4f1\uae09")
            risk_choice = st.selectbox("\ub9ac\uc2a4\ud06c \ub4f1\uae09", _ko_sorted(db_risk_opts))

        c4, c5, c6 = st.columns(3)
        with c4:
            detail_choice = st.selectbox("\ub9ac\uc2a4\ud06c \ub4f1\uae09\ubcc4 \uc138\ubd80 \uc2ec\uc758\uae30\uc900", _dropdown_with_input_option(st.session_state.opt_details))
        with c5:
            db_evid_opts = unique_values_from_db("\uc99d\ube59\uc790\ub8cc\uc720\ud615")
            evidence_choice = st.selectbox("\uc99d\ube59\uc790\ub8cc\uc720\ud615", _dropdown_with_input_option(db_evid_opts))
        with c6:
            alt_choice = st.selectbox("\ub300\uccb4\ud0a4\uc6cc\ub4dc", _dropdown_with_input_option(st.session_state.opt_alt_terms))

        add_click = st.button("\ucd94\uac00", type="primary", key="btn_add_row")

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
                target_list = st.selectbox("대상 목록", _ko_sorted([
                    "상품카테고리", "리스크 등급", "리스크 등급별 세부 심의기준", "증빙자료유형", "대체키워드"
                ]), key="del_list")

            with colm2:
                options_map = {
                    "상품카테고리": st.session_state.opt_categories,
                    "리스크 등급": st.session_state.opt_risks,
                    "리스크 등급별 세부 심의기준": st.session_state.opt_details,
                    "증빙자료유형": st.session_state.opt_evidences,
                    "대체키워드": st.session_state.opt_alt_terms,
                }

                current = options_map.get(target_list, [])
                to_del = st.selectbox("삭제할 값 선택", _ko_sorted(current), key="del_value") if current else None

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
        selection_column = "선택"
        mode_id = "dropdown" if mode == "드롭다운(제한 입력)" else "free"
        draft_key = f"keyword_editor_draft_{mode_id}"
        version_key = "keyword_editor_version"
        if st.session_state.get('keyword_editor_reset_select_all'):
            st.session_state['keyword_editor_reset_select_all'] = False
            st.session_state["keyword_editor_select_all_dropdown"] = False
            st.session_state["keyword_editor_select_all_free"] = False
        if draft_key in st.session_state:
            base_df = pd.DataFrame(st.session_state[draft_key]).rename(
                columns={DISPLAY_F_COL: RAW_F_COL, LAST_SEARCH_LABEL: LAST_HIT_COL}
            )
        else:
            base_df = sort_for_display(st.session_state.kw_df[get_db_cols()].copy())
            base_df.insert(0, selection_column, False)
            st.session_state[draft_key] = _rename_fcol(base_df).to_dict('records')
        editor_version = int(st.session_state.get(version_key, 0))
        editor_key = f"editor_{mode_id}_{editor_version}"
        base_key = f"{editor_key}_base"
        checkbox_key = f"keyword_editor_select_all_{mode_id}"
        display_base_df = _rename_fcol(base_df)
        st.session_state[base_key] = display_base_df.to_dict('records')
        st.session_state.setdefault(
            checkbox_key,
            bool(len(base_df)) and bool(base_df[selection_column].fillna(False).all()),
        )
        st.checkbox(
            "Select all rows",
            key=checkbox_key,
            on_change=_set_keyword_editor_select_all,
            args=(draft_key, base_key, selection_column, version_key, checkbox_key),
            label_visibility="collapsed",
            help="Select or clear all rows in this table.",
        )

        if mode == "드롭다운(제한 입력)":
            from streamlit import column_config as cc
            # Build union option lists including existing DB values
            db_cat_opts = unique_values_from_db("상품카테고리")
            db_risk_opts = unique_values_from_db("리스크 등급")
            db_detail_opts = unique_values_from_db(RAW_F_COL)
            db_alt_opts = unique_values_from_db("대체키워드")
            detail_opts = _dropdown_with_input_option(list(set((st.session_state.opt_details or []) + (db_detail_opts or []))))
            alt_opts = _dropdown_with_input_option(list(set((st.session_state.opt_alt_terms or []) + (db_alt_opts or []))))
            risk_opts = _ko_sorted(set((st.session_state.opt_risks or []) + (db_risk_opts or []))) or _ko_sorted(st.session_state.opt_risks)
            cat_opts = _ko_sorted(set((st.session_state.opt_categories or []) + (db_cat_opts or []))) or _ko_sorted(st.session_state.opt_categories)
            evidence_opts = _ko_sorted(st.session_state.opt_evidences)
            edited_df = st.data_editor(_rename_fcol(
                base_df),
                alt="Editable keyword database",
                on_change=_persist_keyword_editor,
                args=(editor_key, base_key, draft_key, checkbox_key, selection_column),
                column_config={
                    selection_column: cc.CheckboxColumn(label=selection_column),
                    "상품카테고리": cc.SelectboxColumn(options=cat_opts, required=False),
                    "리스크 등급": cc.SelectboxColumn(options=risk_opts, required=False),
                    DISPLAY_F_COL: cc.SelectboxColumn(options=detail_opts, required=False, label=DISPLAY_F_COL),
                    "증빙자료유형": cc.SelectboxColumn(options=evidence_opts, required=False),
                    "대체키워드": cc.SelectboxColumn(options=alt_opts, required=False),
                },
                width="stretch",
                num_rows="fixed" if cloud_enabled() else "dynamic",
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', LAST_SEARCH_LABEL] if cloud_enabled() else [],
                key=editor_key,
            )
        else:
            edited_df = st.data_editor(
                _rename_fcol(base_df),
                alt="Editable keyword database",
                width="stretch",
                num_rows="fixed" if cloud_enabled() else "dynamic",
                disabled=['kwd_no', '키워드 조회 수(누적카운트)', LAST_SEARCH_LABEL] if cloud_enabled() else [],
                column_config={selection_column: st.column_config.CheckboxColumn(label=selection_column)},
                on_change=_persist_keyword_editor,
                args=(editor_key, base_key, draft_key, checkbox_key, selection_column),
                key=editor_key,
            )

        csave, _, _ = st.columns([1, 1, 2])
        with csave:
            if st.button("변경사항 저장", type="primary", key="btn_save_edits"):
                edited_df = edited_df.drop(columns=[selection_column], errors="ignore").fillna("").rename(
                    columns={DISPLAY_F_COL: RAW_F_COL, LAST_SEARCH_LABEL: LAST_HIT_COL}
                )
                try:
                    st.session_state.kw_df = edited_df[get_db_cols()].copy()
                except KeyError:
                    missing = [c for c in get_db_cols() if c not in edited_df.columns]
                    for c in missing:
                        edited_df[c] = ""
                    st.session_state.kw_df = edited_df[get_db_cols()].copy()

                save_db(st.session_state.kw_df, Path(st.session_state.storage_path))
                st.session_state.pop("keyword_editor_draft_dropdown", None)
                st.session_state.pop("keyword_editor_draft_free", None)
                st.session_state[version_key] = editor_version + 1
                st.session_state['keyword_editor_reset_select_all'] = True
                st.success("수정 내용 저장 완료")

        st.caption(f"현재 저장된 항목: {len(st.session_state.kw_df)}")
        _selectable_dataframe(_rename_fcol(sort_for_display(st.session_state.kw_df[get_db_cols()])), width="stretch", alt="Current keyword database")


with tabs['report']:
    st.subheader("📈 분석리포트")

    # 리포트 본문
    log_df = load_hits_log()
    if log_df.empty:
        st.info("조회 로그가 아직 없습니다. 분석을 몇 번 실행하면 리포트가 생성됩니다.")
    else:
        col_r1, col_r2 = st.columns([1, 1], gap="small", vertical_alignment="bottom")
        with col_r1:
            top_n = st.number_input("Top N", min_value=1, max_value=100, value=10, step=1, key="report_topn")
        with col_r2:
            today = now_kst().date()
            default_period = (today - timedelta(days=6), today)
            selected_period = st.date_input(
                "기간",
                value=default_period,
                max_value=today,
                key="report_date_range",
            )
            if not isinstance(selected_period, (tuple, list)) or not selected_period:
                selected_period = default_period
            start_date = selected_period[0]
            end_date = selected_period[1] if len(selected_period) > 1 and selected_period[1] else start_date
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        try:
            _tmp = log_df.copy()
            _tmp["ts_dt"] = pd.to_datetime(_tmp["ts"], errors="coerce")
            mask = (_tmp["ts_dt"] >= start_dt) & (_tmp["ts_dt"] < end_dt_exclusive)
            week_df = _tmp.loc[mask]
            agg = week_df.groupby("kwd_no").size().reset_index(name="기간내_조회수")
            agg = agg.sort_values("기간내_조회수", ascending=False).head(top_n)

            report = agg.merge(st.session_state.kw_df[get_db_cols()], on="kwd_no", how="left")
            report = report.sort_values(["기간내_조회수","kwd_no"], ascending=[False, True], kind="mergesort")
            report = report.reset_index(drop=True)
            report.insert(0, "검색순위", range(1, len(report) + 1))

            # ---- Column order tweak: place '기간내_조회수' right after '대체키워드' ----
            try:
                cols = list(report.columns)
                if "기간내_조회수" in cols:
                    cols.remove("기간내_조회수")
                    if "대체키워드" in cols:
                        idx = cols.index("대체키워드") + 1
                    elif "증빙자료유형" in cols:
                        idx = cols.index("증빙자료유형") + 1
                    else:
                        idx = len(cols)
                    cols.insert(idx, "기간내_조회수")
                    report = report[cols]
            except Exception:
                pass
            # ----------------------------------------------------------------------

            # ---- Right align numeric columns ----
            align_cols = [c for c in ["기간내_조회수", "키워드 조회 수(누적카운트)"] if c in report.columns]
            styled = report.style.set_properties(**{"text-align": "right"}, subset=align_cols)

            _selectable_dataframe(_rename_fcol(styled), width="stretch", hide_index=True, alt="Top keywords for the selected period")
            rep_buf = io.BytesIO()
            report.rename(columns={LAST_HIT_COL: LAST_SEARCH_LABEL}).to_csv(
                rep_buf, index=False, encoding="utf-8-sig"
            )
            st.download_button("리포트 CSV 다운로드 (선택 기간 Top N)", data=rep_buf.getvalue(), file_name="period_topN_report.csv", mime="text/csv", key="dl_week_report")
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
            confirm_reset_all = st.checkbox("전체 조회 수를 0으로 초기화하고 '마지막 검색일자'를 비우기", value=False, key="report_reset_ck")
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

if show_user_management:
    with tabs['user_admin']:
        if message := st.session_state.pop('user_admin_success', None):
            st.success(message)
        render_user_management()

if 'ocr_import' in tabs:
    with tabs['ocr_import']:
        if tabs['ocr_import'].open:
            render_image_ocr_tab()

if 'regulation_chat' in tabs:
    with tabs['regulation_chat']:
        if tabs['regulation_chat'].open:
            render_regulation_chat_tab()

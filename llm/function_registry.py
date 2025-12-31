# function_registry.py
import os
import sys
import json
from typing import Dict, Any, Callable

# Thiết lập đường dẫn đến PROJ của riêng môi trường Conda (do bị xung đột với các biến môi trường khác của máy)
conda_prefix = os.environ.get('CONDA_PREFIX') or r'C:\Users\HIEU\miniconda3\envs\chatbot_conda'
proj_path = os.path.join(conda_prefix, 'Library', 'share', 'proj')
os.environ['PROJ_LIB'] = proj_path

# Import sau khi đã set biến môi trường
import geopandas as gpd
from shapely.geometry import Point

"""
- Định nghĩa danh sách function
"""

# Tạm giữ ở đây; khuyên chuyển vào config.py sau
DIR_THUA_DAT = "data/geojson/thua_dat.geojson"
DIR_QUY_HOACH = "data/geojson/qhpk_sanbaynhatrang_qhsdd.geojson"
DIR_HANH_CHINH = "data/geojson/hanh_chinh.geojson"
PDF_DIR = ""

_HANH_CHINH_INDEX = {}
_THUA_INDEX = {}
_FLAGS = {}

# -----------------------
# Helpers / Schema result
# -----------------------
def _make_error(msg: str) -> Dict[str, Any]:
    return {"status": "error", "message": msg}

def _make_incomplete(msg: str) -> Dict[str, Any]:
    return {"status": "incomplete", "message": msg}

def _make_success(data: Dict[str, Any], field_descriptions: Dict[str, str] = None) -> Dict[str, Any]:
    resp = {"status": "success", "data": data}
    if field_descriptions:
        resp["field_descriptions"] = field_descriptions
    return resp

# tạo mô tả các trường bị thiếu
def build_lookup_result_from_functions(function_name: str, missing_fields: list) -> str:
    """
    Output dạng:
    ma_thua - Mã thửa
    to_ban_do - Số tờ bản đồ
    """

    # tìm function metadata
    fn_meta = next(
        (f for f in functions if f["name"] == function_name),
        None
    )

    if not fn_meta:
        return ""

    params = fn_meta.get("parameters", {})

    lines = []
    for field in missing_fields:
        param = params.get(field, {})
        desc = param.get("description", "")
        lines.append(f"{field} - {desc}")

    return "\n".join(lines)


# function tạo index cho file json
def build_index_once(
    *,
    file_path: str,
    index: Dict[Any, Any],
    loaded_flag: Dict[str, bool],
    flag_name: str,
    key_builder: Callable[[dict], Any],
    value_builder: Callable[[dict], Any],
):
    """
    Build index từ file JSON chỉ 1 lần.

    loaded_flag: dict dùng làm mutable flag
    flag_name: tên flag
    """
    if loaded_flag.get(flag_name):
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for ft in data.get("features", []):
        props = ft.get("properties", {})
        key = key_builder(props)
        if key is not None:
            index[key] = value_builder(props)

    loaded_flag[flag_name] = True

# function tra cứu theo mã
def tra_cuu_thua(json: dict) -> Dict[str, Any]:
    """
    Tra cứu thửa đất theo:
    - Số thửa + số tờ bản đồ (ma_thua, to_ban_do)
    - Hoặc theo tọa độ (lat, lon)
    """
    # Xác định loại truy vấn
    if "ma_thua" in json or "to_ban_do" in json:
        # --- Tra cứu theo mã thửa ---
        ma_thua = json.get("ma_thua")
        to_ban_do = json.get("to_ban_do")

        missing_fields = []
        if not ma_thua:
            missing_fields.append("ma_thua")
        if not to_ban_do:
            missing_fields.append("to_ban_do")

        if missing_fields:
            lookup_result = build_lookup_result_from_functions(
                function_name="tra_cuu_thua_theo_ma",
                missing_fields=missing_fields
            )
            return _make_incomplete(lookup_result)

        ma_thua_norm = str(ma_thua).strip()
        to_ban_do_norm = str(to_ban_do).strip()

        try:
            build_index_once(
                file_path=DIR_HANH_CHINH,
                index=_HANH_CHINH_INDEX,
                loaded_flag=_FLAGS,
                flag_name="hanh_chinh",
                key_builder=lambda p: str(p.get("maxa", "")).strip() or None,
                value_builder=lambda p: {
                    "tenxa": p.get("tenxa"),
                    "tenhuyen": p.get("tenhuyen"),
                    "tentinh": p.get("tentinh"),
                },
            )

            build_index_once(
                file_path=DIR_THUA_DAT,
                index=_THUA_INDEX,
                loaded_flag=_FLAGS,
                flag_name="thua",
                key_builder=lambda p: (str(p.get("soto", "")).strip(),
                                       str(p.get("sothua", "")).strip()),
                value_builder=lambda p: p,
            )
        except Exception as e:
            return _make_error(f"Lỗi tải dữ liệu: {str(e)}")

        props = _THUA_INDEX.get((to_ban_do_norm, ma_thua_norm))
        if not props:
            return {
                "status": "not_found",
                "message": f"Không tìm thấy thửa đất với số tờ = '{to_ban_do_norm}', số thửa = '{ma_thua_norm}'"
            }

        hc = _HANH_CHINH_INDEX.get(str(props.get("maxa", "")).strip(), {})

        data_out = {
            "soto": to_ban_do_norm,
            "sothua": ma_thua_norm,
            "dientich": props.get("dientich"),
            "maloaidat": props.get("maloaidat"),
            "diachithua": props.get("diachithua"),
            "duongthua": props.get("duongthua"),
            "chusudung": props.get("chusudung1"),
            "diachi_csd": props.get("diachi_csd"),
            "ghichu": props.get("ghichu"),
            **hc
        }

        field_descriptions = {
            "soto": "Số tờ bản đồ",
            "sothua": "Số thửa đất/mã thửa",
            "dientich": "Diện tích thửa đất (m²)",
            "maloaidat": "Mã loại đất (ODT - ở đô thị, DGT - đất giao thông, SKC - đất cơ sở sản xuất phi nông nghiệp)",
            "duongthua": "Tên đường nơi có thửa đất",
            "chusudung": "Tên chủ sử dụng đất hợp pháp",
            "diachithua": "Địa chỉ thửa đất",
            "diachi_csd": "Địa chỉ chủ sử dụng đất",
            "ghichu": "Ghi chú",
            "tenxa": "Tên xã/phường",
            "tenhuyen": "Tên huyện/thành phố",
            "tentinh": "Tên tỉnh"
        }

        return _make_success(data_out, field_descriptions)

    elif "lat" in json or "lon" in json:
        # --- Tra cứu theo tọa độ ---
        lat = json.get("lat")
        lon = json.get("lon")

        missing_fields = []
        if not lat:
            missing_fields.append("lat")
        if not lon:
            missing_fields.append("lon")

        if missing_fields:
            lookup_result = build_lookup_result_from_functions(
                function_name="tra_cuu_thua_theo_toa_do",
                missing_fields=missing_fields
            )
            return _make_incomplete(lookup_result)

        try:
            gdf = gpd.read_file(DIR_THUA_DAT, encoding="utf-8")
        except Exception as e:
            return _make_error(f"Không thể đọc file GeoJSON: {str(e)}")

        point = Point(float(lon), float(lat))
        match = gdf[gdf.contains(point)]

        if match.empty:
            return {"status": "not_found",
                    "message": f"Không tìm thấy quy hoạch với tọa độ lat = '{lat}', lon = '{lon}'"}

        data = match.iloc[0].to_dict()

        try:
            build_index_once(
                file_path=DIR_HANH_CHINH,
                index=_HANH_CHINH_INDEX,
                loaded_flag=_FLAGS,
                flag_name="hanh_chinh",
                key_builder=lambda p: str(p.get("maxa", "")).strip() or None,
                value_builder=lambda p: {
                    "tenxa": p.get("tenxa"),
                    "tenhuyen": p.get("tenhuyen"),
                    "tentinh": p.get("tentinh"),
                },
            )
        except Exception as e:
            return _make_error(f"Lỗi tải dữ liệu: {str(e)}")

        hc = _HANH_CHINH_INDEX.get(str(data.get("maxa", "")).strip(), {})

        data_out = {
            "lat": lat,
            "lon": lon,
            "soto": data.get("soto"),
            "sothua": data.get("sothua"),
            "dientich": data.get("dientich"),
            "maloaidat": data.get("maloaidat"),
            "diachithua": data.get("diachithua"),
            "duongthua": data.get("duongthua"),
            "chusudung": data.get("chusudung1"),
            "diachi_csd": data.get("diachi_csd"),
            "ghichu": data.get("ghichu"),
            **hc
        }

        field_descriptions = {
            "lat": "Vĩ độ",
            "lon": "Kinh độ",
            "soto": "Số tờ bản đồ",
            "sothua": "Số thửa đất/mã thửa đất",
            "dientich": "Diện tích thửa đất (m²)",
            "maloaidat": "Mã loại đất (ODT - ở đô thị, DGT - đất giao thông, SKC - đất cơ sở sản xuất phi nông nghiệp)",
            "duongthua": "Tên đường nơi có thửa đất",
            "chusudung": "Tên chủ sử dụng đất hợp pháp",
            "diachithua": "Địa chỉ thửa đất",
            "diachi_csd": "Địa chỉ chủ sử dụng đất",
            "ghichu": "Ghi chú",
            "tenxa": "Tên xã/phường",
            "tenhuyen": "Tên huyện/thành phố",
            "tentinh": "Tên tỉnh"
        }

        return _make_success(data_out, field_descriptions)

    else:
        # Không có dữ liệu cần thiết
        return _make_incomplete("Thiếu tham số tra cứu: yêu cầu 'ma_thua + to_ban_do' hoặc 'lat + lon'")



# function tra cứu quy hoạch theo tọa độ
def tra_cuu_quy_hoach(json: dict) -> Dict[str, Any]:
    """
    Tra cứu quy hoạch theo tọa độ từ GeoJSON.
    - gdf: geopandas.GeoDataFrame chứa dữ liệu GeoJSON
    """
    lat = json.get("lat")
    lon = json.get("lon")
    
    # Validate
    missing_fields = []
    if not lat:
        missing_fields.append("lat")
    if not lon:
        missing_fields.append("lon")

    if (missing_fields):
        lookup_result = build_lookup_result_from_functions(
            function_name="tra_cuu_quy_hoach",
            missing_fields=missing_fields
        )

        return _make_incomplete(lookup_result)

    # Load geojson
    try:
        gdf = gpd.read_file(DIR_QUY_HOACH, encoding="utf-8")
    except Exception as e:
        return _make_error(f"Không thể đọc file GeoJSON: {str(e)}")

    # Tạo Point từ tọa độ (lưu ý GeoJSON dùng (lon, lat))
    point = Point(float(lon), float(lat))

    # Tìm polygon chứa point
    match = gdf[gdf.contains(point)]
    data = match.iloc[0].to_dict()

    if not match.empty:
        data_out = {
            "lat": lat,
            "lon": lon,
            "maloaisdd" : data.get("maloaisdd"),
            "tenloaisdd" : data.get("tenloaisdd"),
            "kyhieuloda" : data.get("kyhieuloda"),
            "sotangtoid" : data.get("sotangtoid"),
            "dientich" : data.get("dientich"),
            "matdoxd" : data.get("matdoxd")
        }

        field_descriptions = {
            "lat": "Vĩ độ",
            "lon": "Kinh độ",
            "maloaisdd": "Mã loại đất quy hoạch (DGD - Đất xây dựng cơ sở giáo dục và đào tạo, DGT - Đất công trình giao thông)",
            "tenloaisdd": "Tên loại đất quy hoạch",
            "kyhieuloda": "Ký hiệu lô đất",
            "sotangtoid": "Số tầng tối đa quy hoạch",
            "dientich": "Diện tích quy hoạch (m²)",
            "matdoxd": "Mật độ xây dựng quy hoạch (%)"
        }

        return _make_success(data_out, field_descriptions)
    
    return {"status": "not_found", "message": f"Không tìm thấy quy hoạch với tọa độ lat = '{lat}', lon = '{lon}'"}

def tom_tat_van_ban(json: dict):
    van_ban = json.get("van_ban")
    # Validate
    missing_fields = []
    if not van_ban:
        missing_fields.append("van_ban")

    if (missing_fields):
        lookup_result = build_lookup_result_from_functions(
            function_name="tom_tat_van_ban",
            missing_fields=missing_fields
        )

        return _make_incomplete(lookup_result)
    
    return {"status": "summary", "message": van_ban}


def hoi_dap_quy_hoach(json: dict):
    return {"status": "normal"}

def hoi_thoai_chung(json: dict):
    return {"status": "normal"}

# danh sách mô tả function
functions = [
    {
        "name": "tra_cuu_quy_hoach_thua_theo_ma",
        "description": "Tra cứu thông tin quy hoạch thửa đất theo mã thửa và tờ bản đồ.",
        "parameters": {
            "ma_thua": {"type": "string", "description": "Thửa/mã thửa (Ví dụ: 123)"},
            "to_ban_do": {"type": "string", "description": "Tờ/tờ bản đồ (Ví dụ: 50)"}
        },
        "required": ["ma_thua", "to_ban_do"],
        "callable": tra_cuu_thua,
        "suggestion_templates": [
            "Tra cứu các thửa đất liền kề với thửa {ma_thua} tờ {to_ban_do}",
            "Xem danh sách tất cả các thửa thuộc cùng tờ bản đồ {to_ban_do}",
            "Kiểm tra chi tiết biến động/tranh chấp của thửa {ma_thua} tờ {to_ban_do}",
            "Tính toán tiền sử dụng đất khi chuyển đổi mục đích tại thửa {ma_thua}"
        ]
    },
    {
        "name": "tra_cuu_quy_hoach_thua_theo_toa_do",
        "description": "Tra cứu thông tin quy hoạch thửa đất bằng tọa độ GPS (lat, lon).",
        "parameters": {
            "lat": {"type": "number", "description": "Vĩ độ (Ví dụ: 10.8234)"},
            "lon": {"type": "number", "description": "Kinh độ (Ví dụ: 106.6297)"}
        },
        "required": ["lat", "lon"],
        "callable": tra_cuu_thua
    },
    {
        "name": "tra_cuu_quy_hoach_san_bay_nha_trang_theo_toa_do",
        "description": "Tra cứu quy hoạch phân khu sân bay nha trang theo tọa độ GPS (lat, lon).",
        "parameters": {
            "lat": {"type": "number", "description": "Vĩ độ (Ví dụ: 10.8234)"},
            "lon": {"type": "number", "description": "Kinh độ (Ví dụ: 106.6297)"}
        },
        "required": ["lat", "lon"],
        "callable": tra_cuu_quy_hoach
    },
    {
        "name": "tom_tat_van_ban",
        "description": "Tóm tắt một văn bản được cung cấp trực tiếp trong câu hỏi.",
        "parameters": {
            "van_ban": {"type": "string","description": "Văn bản cần tóm tắt."}
        },
        "required": ["van_ban"],
        "callable": tom_tat_van_ban
    },
    {
        "name": "hoi_dap_quy_hoach",
        "description": "Các câu hỏi chung về quy hoạch sử dụng đất, pháp luật đất đai, quy trình hành chính, khái niệm chuyên ngành.",
        "parameters": {},
        "callable": hoi_dap_quy_hoach
    },
    {
        "name": "hoi_thoai_chung",
        "description": "Xử lý các câu chào hỏi, cảm ơn, yêu cầu tiếp tục, hoặc yêu cầu lặp lại câu trả lời trước đó.",
        "parameters": {},
        "callable": hoi_thoai_chung
    }
]

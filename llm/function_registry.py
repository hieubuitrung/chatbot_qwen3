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
_THUA_THEO_TO_INDEX = {}
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
    multi_value: bool = False # Thêm tham số để kiểm soát việc ghi đè hay cộng dồn
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
            val = value_builder(props)
            if multi_value:
                # Nếu cho phép nhiều giá trị (ví dụ: nhiều thửa trong 1 tờ)
                if key not in index:
                    index[key] = []
                index[key].append(val)
            else:
                # Nếu chỉ cần 1 giá trị duy nhất (truy xuất nhanh 1 đối tượng)
                index[key] = val

    loaded_flag[flag_name] = True

# xử lý giá trị 
def clean_val(val, default="Đang cập nhật"):
    # Nếu là None hoặc không phải chuỗi
    if val is None:
        return default
    
    # Ép kiểu về string và xóa khoảng trắng 2 đầu
    str_val = str(val).strip()
    
    # Nếu là chuỗi rỗng sau khi strip hoặc là chữ "none" (thường gặp trong db)
    if str_val == "" or str_val.lower() == "none":
        return default
        
    return str_val

# function tra cứu theo mã
def tra_cuu_thua(json_input: dict) -> Dict[str, Any]:
    """
    Tra cứu thửa đất theo:
    - Số thửa + số tờ bản đồ (ma_thua, to_ban_do)
    - Chỉ số tờ bản đồ (to_ban_do) -> Trả về danh sách thửa
    - Hoặc theo tọa độ (lat, lon)
    """
    # 1. Khởi tạo mô tả trường dữ liệu chung
    field_descriptions = {
        "soto": "Số tờ bản đồ",
        "sothua": "Số thửa đất/mã thửa",
        "dientich": "Diện tích thửa đất (m²)",
        "maloaidat": "Mã loại đất (Ví dụ: ODT, DGT, SKC...)",
        "duongthua": "Tên đường nơi có thửa đất",
        "chusudung": "Tên chủ sử dụng đất hợp pháp",
        "diachithua": "Địa chỉ thửa đất",
        "diachi_csd": "Địa chỉ chủ sử dụng đất",
        "ghichu": "Ghi chú",
        "tenxa": "Tên xã/phường",
        "tenhuyen": "Tên huyện/thành phố",
        "tentinh": "Tên tỉnh",
        "lat": "Vĩ độ",
        "lon": "Kinh độ"
    }

    try:
        # 2. Luôn đảm bảo index Hành chính được load (dùng chung cho mọi case)
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
        return _make_error(f"Lỗi tải dữ liệu hành chính: {str(e)}")

    # --- CASE 1: TRA CỨU THEO TỜ/THỬA ---
    if "to_ban_do" in json_input:
        to_ban_do = str(json_input.get("to_ban_do", "")).strip()
        ma_thua = str(json_input.get("ma_thua", "")).strip() if json_input.get("ma_thua") else None

        if not to_ban_do:
            return _make_incomplete(build_lookup_result_from_functions("tra_cuu", ["to_ban_do"]))

        try:
            # CASE 1.1: CÓ CẢ TỜ VÀ THỬA (Chi tiết 1 thửa)
            if ma_thua:
                build_index_once(
                    file_path=DIR_THUA_DAT,
                    index=_THUA_INDEX,
                    loaded_flag=_FLAGS,
                    flag_name="thua",
                    key_builder=lambda p: (str(p.get("soto", "")).strip(), str(p.get("sothua", "")).strip()),
                    value_builder=lambda p: p,
                )
                props = _THUA_INDEX.get((to_ban_do, ma_thua))
                
                if not props:
                    return {"status": "not_found", "message": f"Không tìm thấy thửa {ma_thua} trong tờ {to_ban_do}"}

                hc = _HANH_CHINH_INDEX.get(str(props.get("maxa", "")).strip(), {})
                data_out = {
                    "soto": to_ban_do, "sothua": ma_thua,
                    "dientich": clean_val(props.get("dientich")),
                    "maloaidat": clean_val(props.get("maloaidat")),
                    "diachithua": clean_val(props.get("diachithua")),
                    "duongthua": clean_val(props.get("duongthua")),
                    "chusudung": clean_val(props.get("chusudung1"), default="Chưa xác định"),
                    "diachi_csd": clean_val(props.get("diachi_csd")),
                    "ghichu": clean_val(props.get("ghichu"), default="Không có ghi chú"),
                    **hc
                }
                return _make_success(data_out, field_descriptions)

            # CASE 1.2: CHỈ CÓ TỜ (Danh sách các thửa)
            else:
                build_index_once(
                    file_path=DIR_THUA_DAT,
                    index=_THUA_THEO_TO_INDEX,
                    loaded_flag=_FLAGS,
                    flag_name="thua_theo_to",
                    key_builder=lambda p: str(p.get("soto", "")).strip() or None,
                    value_builder=lambda p: {"sothua": p.get("sothua"), "maloaidat": p.get("maloaidat"), "dientich": p.get("dientich")},
                    multi_value=True # Sử dụng tính năng multi-value đã sửa
                )
                list_thua = _THUA_THEO_TO_INDEX.get(to_ban_do)
                if not list_thua:
                    return {"status": "not_found", "message": f"Không tìm thấy dữ liệu cho tờ bản đồ số {to_ban_do}"}
                
                return _make_success(
                    {"to_ban_do": to_ban_do, "danh_sach_thua": list_thua},
                    {"danh_sach_thua": f"Danh sách các thửa đất thuộc tờ bản đồ {to_ban_do}"}
                )

        except Exception as e:
            return _make_error(f"Lỗi xử lý file thửa đất: {str(e)}")

    # --- CASE 2: TRA CỨU THEO TỌA ĐỘ ---
    elif "lat" in json_input or "lon" in json_input:
        lat = json_input.get("lat")
        lon = json_input.get("lon")

        if not lat or not lon:
            return _make_incomplete(build_lookup_result_from_functions("tra_cuu_toa_do", ["lat", "lon"]))

        try:
            # Lưu ý: Nên đưa việc load gdf ra ngoài hàm để tối ưu hiệu năng (Global)
            gdf = gpd.read_file(DIR_THUA_DAT, encoding="utf-8")
            point = Point(float(lon), float(lat))
            match = gdf[gdf.contains(point)]

            if match.empty:
                return {"status": "not_found", "message": f"Tọa độ ({lat}, {lon}) không nằm trong thửa đất nào."}

            data = match.iloc[0].to_dict()
            hc = _HANH_CHINH_INDEX.get(str(data.get("maxa", "")).strip(), {})

            data_out = {
                "lat": lat, "lon": lon,
                "soto": data.get("soto"), "sothua": data.get("sothua"),
                "dientich": clean_val(data.get("dientich")),
                "maloaidat": clean_val(data.get("maloaidat")),
                "diachithua": clean_val(data.get("diachithua")),
                "duongthua": clean_val(data.get("duongthua")),
                "chusudung": clean_val(data.get("chusudung1"), default="Chưa xác định"),
                "diachi_csd": clean_val(data.get("diachi_csd")),
                "ghichu": clean_val(data.get("ghichu"), default="Không có ghi chú"),
                **hc
            }
            return _make_success(data_out, field_descriptions)
        except Exception as e:
            return _make_error(f"Lỗi xử lý tọa độ: {str(e)}")

    # --- CASE 3: THIẾU THÔNG TIN ---
    return _make_incomplete("Vui lòng cung cấp số tờ (to_ban_do) hoặc tọa độ (lat, lon) để tra cứu.")



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
        "required": ["to_ban_do"],
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

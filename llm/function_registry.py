# function_registry.py
import os
import sys
import json
from typing import Dict, Any, Callable, List
from types import SimpleNamespace
import psycopg2
from psycopg2.extras import RealDictCursor

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

# Thông tin kết nối DB
DB_CONFIG = {
    "dbname": "dubaonguonnuoc",
    "user": "postgres",
    "password": "penta@321",
    "host": "vbeta.net",
    "port": "5433"
}

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
                    value_builder=lambda p: p,
                    multi_value=True # Sử dụng tính năng multi-value đã sửa
                )
                list_thua = _THUA_THEO_TO_INDEX.get(to_ban_do)
                if not list_thua:
                    return {"status": "not_found", "message": f"Không tìm thấy dữ liệu cho tờ bản đồ số {to_ban_do}"}
                
                field_descriptions.update({
                    "soluongthua": "Tổng số lượng thửa đất có trong tờ bản đồ này",
                    "tongdientich": "Tổng diện tích tất cả thửa đất trong tờ bản đồ này (m²)",
                    "loaidat_dientich": "Tổng diện tích phân theo loại đất trong tờ bản đồ này",
                    "cactuyenduong": "Danh sách các tuyến đường có thửa đất trong tờ bản đồ này"
                })

                # Khởi tạo dictionary để cộng dồn diện tích theo loại đất
                hc = _HANH_CHINH_INDEX.get(str(list_thua[0].get("maxa", "")).strip(), {})
                area_by_type = {}
                total_area = 0

                for item in list_thua:
                    maloai = item.get("maloaidat") or "chưa xác định"
                    # Đảm bảo dientich là số thực để tính toán
                    try:
                        dt = float(item.get("dientich") or 0)
                    except (ValueError, TypeError):
                        dt = 0
                    
                    # Cộng dồn vào diện tích tổng
                    total_area += dt
                    
                    # Cộng dồn vào từng loại đất cụ thể
                    if maloai in area_by_type:
                        area_by_type[maloai] += dt
                    else:
                        area_by_type[maloai] = dt


                # Làm tròn số sau khi tính toán xong
                area_by_type = {k: round(v, 2) for k, v in area_by_type.items()}

                data = {
                    "soluongthua": len(list_thua),
                    "tongdientich": round(total_area, 2),
                    "loaidat_dientich": area_by_type,  # Kết quả: {'ONT': 500.5, 'CLN': 1200.0}
                    "cactuyenduong": list(set(item.get("duongthua") for item in list_thua if item.get("duongthua").strip())),
                    "soto": to_ban_do,
                    **hc
                }

                return _make_success(data, field_descriptions)

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

def execute_select_query(query: str, values: tuple = ()):
    """Hàm dùng chung để thực thi các câu lệnh SELECT và trả về List[Dict]"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, values)
            return cur.fetchall()
    except Exception as e:
        print(f"Database Error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def build_dynamic_where(base_query: str, params: dict):
    """Tự động tạo câu SQL và Tuple values từ Dictionary"""
    conditions = []
    values = []
    
    for field, value in params.items():
        if value is not None and value != "":
            conditions.append(f"unaccent(LOWER({field})) ILIKE unaccent(LOWER(%s))")
            search_value = value.replace(" ", "%")
            values.append(f"%{search_value}%")
            
    query = base_query
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    return query, tuple(values)

def tra_cuu_cong_trinh(params_json: dict):
    # 1. Gọi hàm xây dựng query
    query, values = build_dynamic_where("SELECT * FROM c.congtrinh", params_json)
    
    # 2. Nếu không có điều kiện, có thể giới hạn kết quả
    if not values:
        query += " LIMIT 1"
        # return _make_incomplete("Vui lòng cung cấp thông tin về công trình để có thể tra cứu.")
        
    # 3. Gọi hàm thực thi dùng chung
    data = execute_select_query(query, values)
    
    clean_objects = [dict(row) for row in data] if data else []

    # 2. Loại bỏ các trường dữ liệu rác ngay từ đầu (như 'geom') để nhẹ máy
    for obj in clean_objects:
        obj.pop('geom', None)

    # 3. Đóng gói vào biến result
    result = {
        "status": "success" if data is not None else "error",
        "data": clean_objects  # Trả về danh sách các dictionary sạch
    }
    print("tra_cuu_cong_trinh result:", result)

    return _make_success(result)



# danh sách mô tả function
functions = [
    {
        "name": "tra_cuu_cong_trinh",
        "description": "Tra cứu thông tin danh mục, thuộc tính và đặc điểm kỹ thuật của các công trình thủy lợi. Dùng khi người dùng hỏi về: tên, vị trí (xã/huyện/tỉnh), loại hình (đập, cống, trạm bơm), năm xây dựng, đơn vị quản lý hoặc quy mô công trình.",
        "parameters": {
            "ten": {"type": "string", "description": "Tên gọi hoặc tên chính thức của công trình."},
            "ma": {"type": "string", "description": "Mã định danh hoặc tên gọi riêng của công trình (ví dụ: 'H45.TL0008.HC001')."},
            "loaicongtrinh": {"type": "string", "description": "Phân loại công trình. Ví dụ: 'Hồ chứa', 'Hệ thống hỗn hợp', 'Trạm bơm', 'Cống', 'Hồ chứa TĐ', 'HT tiêu', 'Đập dâng'."},
            "namxd": {"type": "number", "description": "Năm công trình được xây dựng hoặc đưa vào sử dụng (ví dụ: 1998)."},
            "vung": {"type": "string", "description": "Vùng thủy lợi hoặc vùng kinh tế (ví dụ: 'Trung Quốc', 'Đồng bằng SCL', 'Bắc Trung Bộ')."},
            "matinh": {"type": "string", "description": "Tên hoặc mã tỉnh/thành phố nơi công trình tọa lạc."},
            "mahuyen": {"type": "string", "description": "Tên hoặc mã quận/huyện nơi công trình tọa lạc."},
            "maxa": {"type": "string", "description": "Tên hoặc mã phường/xã nơi công trình tọa lạc."},
            "dvql": {"type": "string", "description": "Tên đơn vị hoặc tổ chức chịu trách nhiệm quản lý vận hành công trình."},
            "luuvuc": {"type": "string", "description": "Hệ thống lưu vực sông mà công trình thuộc về (ví dụ: 'Sông Đà', 'Sông Cả')."},
            "x": {"type": "number", "description": "Tọa độ lon (kinh độ) của công trình"},
            "y": {"type": "number", "description": "Tọa độ lat (vĩ độ) của công trình"},
            "phanloailonnho": {"type": "string", "description": "Quy mô phân loại của công trình. Giá trị có thể là: 'Lớn', 'Vừa', 'Nhỏ'."}
        },
        "required": [],
        "callable": tra_cuu_cong_trinh,
    },
    # {
    #     "name": "tra_cuu_quy_hoach_theo_to",
    #     "description": "Tra cứu thông tin quy hoạch chỉ theo tờ bản đồ.",
    #     "parameters": {
    #         "to_ban_do": {"type": "string", "description": "Tờ/tờ bản đồ (Ví dụ: 50)"}
    #     },
    #     "required": ["to_ban_do"],
    #     "callable": tra_cuu_thua,
    #     "suggestion_templates": [
    #         "Tính tổng diện tích các thửa đất trong tờ bản đồ này.",
    #         "Xem danh sách các loại đất và diện tích tương ứng trong tờ bản đồ này.",
    #         "Tờ bản đồ thuộc xã/phường nào?"
    #     ]
    # },
    # {
    #     "name": "tra_cuu_quy_hoach_thua_theo_ma",
    #     "description": "Tra cứu thông tin quy hoạch thửa đất theo mã thửa và tờ bản đồ.",
    #     "parameters": {
    #         "ma_thua": {"type": "string", "description": "Thửa/mã thửa (Ví dụ: 123)"},
    #         "to_ban_do": {"type": "string", "description": "Tờ/tờ bản đồ (Ví dụ: 50)"}
    #     },
    #     "required": ["to_ban_do", "ma_thua"],
    #     "callable": tra_cuu_thua,
    #     "suggestion_templates": [
    #         "Tra cứu các thửa đất liền kề với thửa đất này.",
    #         "Tính toán tiền sử dụng đất khi chuyển đổi mục đích tại thửa đất này."
    #     ]
    # },
    # {
    #     "name": "tra_cuu_quy_hoach_thua_theo_toa_do",
    #     "description": "Tra cứu thông tin quy hoạch thửa đất bằng tọa độ GPS (lat, lon).",
    #     "parameters": {
    #         "lat": {"type": "number", "description": "Vĩ độ (Ví dụ: 10.8234)"},
    #         "lon": {"type": "number", "description": "Kinh độ (Ví dụ: 106.6297)"}
    #     },
    #     "required": ["lat", "lon"],
    #     "callable": tra_cuu_thua
    # },
    # {
    #     "name": "tra_cuu_quy_hoach_san_bay_nha_trang_theo_toa_do",
    #     "description": "Tra cứu quy hoạch phân khu sân bay nha trang theo tọa độ GPS (lat, lon).",
    #     "parameters": {
    #         "lat": {"type": "number", "description": "Vĩ độ (Ví dụ: 10.8234)"},
    #         "lon": {"type": "number", "description": "Kinh độ (Ví dụ: 106.6297)"}
    #     },
    #     "required": ["lat", "lon"],
    #     "callable": tra_cuu_quy_hoach
    # },
    # {
    #     "name": "tom_tat_van_ban",
    #     "description": "Tóm tắt một văn bản được cung cấp trực tiếp trong câu hỏi.",
    #     "parameters": {
    #         "van_ban": {"type": "string","description": "Văn bản cần tóm tắt."}
    #     },
    #     "required": ["van_ban"],
    #     "callable": tom_tat_van_ban
    # },
    {
        "name": "hoi_dap_chung",
        "description": "Các câu hỏi chung về thủy lợi, pháp luật, quy trình, khái niệm chuyên ngành.",
        "parameters": {},
        "callable": hoi_dap_quy_hoach
    },
    # {
    #     "name": "hoi_thoai_chung",
    #     "description": "Xử lý các câu chào hỏi, cảm ơn, yêu cầu tiếp tục, hoặc yêu cầu lặp lại câu trả lời trước đó.",
    #     "parameters": {},
    #     "callable": hoi_thoai_chung
    # }
]

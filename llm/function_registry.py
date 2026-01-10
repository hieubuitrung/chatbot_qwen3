from typing import Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

# Thiết lập đường dẫn đến PROJ của riêng môi trường Conda (do bị xung đột với các biến môi trường khác của máy)
# conda_prefix = os.environ.get('CONDA_PREFIX') or r'C:\Users\HIEU\miniconda3\envs\chatbot_conda'
# proj_path = os.path.join(conda_prefix, 'Library', 'share', 'proj')
# os.environ['PROJ_LIB'] = proj_path

# Import sau khi đã set biến môi trường
# import geopandas as gpd
# from shapely.geometry import Point

"""
- Định nghĩa danh sách function
"""

# Thông tin kết nối DB
DB_CONFIG = {
    "dbname": "",
    "user": "",
    "password": "",
    "host": "",
    "port": ""
}

# -----------------------
# Helpers / Schema result
# -----------------------
def _make_error(msg: str) -> Dict[str, Any]:
    return {"status": "error", "message": msg}

def _make_success(count_result, data: Dict[str, Any], field_descriptions: Dict[str, str] = None) -> Dict[str, Any]:
    resp = {"status": "success", "data": data, "count": count_result}
    if field_descriptions:
        resp["field_descriptions"] = field_descriptions
    return resp

def hoi_dap_chung(table_name, hints, parameters, params_json: dict):
    return {"status": "normal"}

def execute_select_query(query: str, values: tuple = ()):
    """Hàm dùng chung để thực thi các câu lệnh SELECT và trả về List[Dict]"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, values)
            rows = cur.fetchall()
            return {
                "ok": True,
                "data": rows
            }
    except Exception as e:
        print(f"Database Error: {e}")
        return {
            "ok": False,
            "error_type": "DB_CONNECTION_ERROR",
            "message": str(e)
        }
    finally:
        if conn:
            conn.close()

def build_query(base_query, params_json):
    conditions = []
    values = []
    params = params_json.get("conditions", [])
    order = params_json.get("orders", [])
    limit = params_json.get("limit", None)

    # Bản đồ ánh xạ toán tử từ JSON sang SQL
    operator_map = {
        "eq": "=",
        "neq": "<>",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "like": "ILIKE"
    }

    for condition in params:
        field = condition.get("field")
        op_key = condition.get("operator", "eq") # Mặc định là 'eq' nếu không có
        value = condition.get("value")

        # Kiểm tra giá trị hợp lệ (chấp nhận số 0 nhưng bỏ qua None/Rỗng)
        if value is not None and value != "":
            sql_op = operator_map.get(op_key, "ILIKE") # Mặc định là ILIKE nếu không tìm thấy

            if sql_op == "ILIKE":
                # Xử lý riêng cho tìm kiếm chuỗi
                conditions.append(f"unaccent(LOWER({field}::text)) ILIKE unaccent(LOWER(%s))")
                search_value = str(value).replace(" ", "%")
                values.append(f"%{search_value}%")
            else:
                # Xử lý cho các phép so sánh số, ngày tháng, bằng nhau
                conditions.append(f"{field} {sql_op} %s")
                values.append(value)

    query = base_query
    if conditions:
        prefix = " AND " if " WHERE " in query.upper() else " WHERE "
        query += prefix + " AND ".join(conditions)
    
    if order:
        order_clauses = [f"{o.get('field')} {o.get('direction', 'ASC').upper()}" for o in order]
        query += " ORDER BY " + ", ".join(order_clauses)
    
    if limit:
        query += " LIMIT %s"
        values.append(limit > 10 and 10 or limit)  # Giới hạn tối đa 20 bản ghi
    else :
        query += " LIMIT 10"  # Mặc định giới hạn 20 bản ghi nếu không có limit

    return query, tuple(values)

def tra_cuu_cong_trinh(table_name, hints, parameters, params_json: dict):
    cols = []
    field_descriptions = {}

    if (table_name is None):
        return _make_error("Hệ thống đang tạm thời gián đoạn, chưa thể truy xuất dữ liệu do sự cố kỹ thuật ngoài ý muốn.\nVui lòng thử lại sau ít phút hoặc quay lại sau.")
    
    for key, value in parameters.items():
        cols.append(f'{key} AS "{key}"')
        field_descriptions[key] = value.get("description", "")
    
    join_clauses = []
    for hint in hints:  # hints là list bạn đưa ra
        join_type = hint.get("type", "left").upper()
        table = hint["table"]
        alias = hint.get("alias")
                
        # Ghép các điều kiện ON bằng AND
        on_conditions = " AND ".join(hint["on"])  # hint["on"] là list[str] → OK
        
        # Xây dựng clause
        clause = f"{join_type} JOIN {table} AS {alias} ON {on_conditions}"
        join_clauses.append(clause)

    # Ghép tất cả thành chuỗi JOIN
    joins_sql = " ".join(join_clauses)
    base_query = f"SELECT {', '.join(cols)} FROM {table_name} {joins_sql}"
    # 1. Gọi hàm xây dựng query
    query, values = build_query(base_query, params_json)

    limit = params_json.get("limit", None)
    count_data = limit
    if not limit:
        count_query = f"SELECT COUNT(*) FROM {table_name} {joins_sql}"
        query_count, values_count = build_query(count_query, {"conditions": params_json.get("conditions", [])})
        count_result = execute_select_query(query_count, values_count)
        data_list = count_result.get("data", [])
        count_data = data_list[0].get('count', None)

    print("DEBUG - Count:", count_data)
    print("DEBUG - Query:", query, query_count)
    print("DEBUG - Values:", values, values_count)
    
        
    # 3. Gọi hàm thực thi dùng chung
    result = execute_select_query(query, values)
    
    
    # nếu có lỗi xảy ra khi truy xuất DB
    if (result.get("ok") is False):
        return _make_error("Hệ thống đang tạm thời gián đoạn, chưa thể truy xuất dữ liệu do sự cố kỹ thuật ngoài ý muốn.\nVui lòng thử lại sau ít phút hoặc quay lại sau.")
    
    data = result.get("data", [])
    
    clean_objects = [dict(row) for row in data] if data else []
    
    return _make_success(count_data, clean_objects, field_descriptions)



# danh sách mô tả function
functions = [
    {
        "name": "tra_cuu_cong_trinh",
        "table_name": "c.congtrinh",
        "description": "Tra cứu thông tin danh mục, thuộc tính và đặc điểm kỹ thuật của các công trình thủy lợi. Dùng khi người dùng hỏi về: tên, vị trí (xã/huyện/tỉnh), loại hình (đập, cống, trạm bơm), năm xây dựng, đơn vị quản lý hoặc quy mô công trình.",
        "join": [
            {"table": "c.hanhchinh", "type": "left", "alias": "tinh", "on": ["c.congtrinh.matinh = tinh.pcode", "tinh.cap = 1"]},
            {"table": "c.hanhchinh", "type": "left", "alias": "huyen", "on": ["c.congtrinh.mahuyen = huyen.dcode", "huyen.cap = 2"]},
            {"table": "c.hanhchinh", "type": "left", "alias": "xa", "on": ["c.congtrinh.maxa = xa.ccode", "xa.cap = 3"]}
        ],
        "parameters": {
            "ten": {"type": "string", "description": "Tên công trình", "example": "TB. Lộc Giang B"},
            "ma": {"type": "string", "description": "Mã công trình", "example": "H45.TL0008.HC001"},
            "loaicongtrinh": {"type": "string", "description": "Loại công trình", "example": "Trạm bơm, Hồ chứa, Hệ thống hỗn hợp, Cống, Đập dâng"},
            "namxd": {"type": "number", "description": "Năm xây dựng", "example": "1998"},
            "vung": {"type": "string", "description": "Vùng", "example": "Trung Quốc, Đồng bằng SCL, Bắc Trung Bộ"},
            "tinh.name": {"type": "string", "description": "Tỉnh/Thành phố", "example": "Hải Dương"},
            "huyen.name": {"type": "string", "description": "Quận/Huyện", "example": "Nam Sách"},
            "xa.name": {"type": "string", "description": "Xã/Phường", "example": "Cộng Hòa"},
            "dvql": {"type": "string", "description": "Đơn vị quản lý", "example": "Phòng NN&PTNT"},
            "luuvuc": {"type": "string", "description": "Lưu vực", "example": "Sông Mê Công"},
            "x": {"type": "number", "description": "X (WGS 84)", "example": "109.0468"},
            "y": {"type": "number", "description": "Y (WGS 84)", "example": "21.541766"},
            "phanloailonnho": {"type": "string", "description": "Phân loại (lớn/nhỏ)", "example": "Lớn"},
            "flv": {"type": "number", "description": "Diện tích lưu vực (km2)", "example": "160.3"},
            "whi": {"type": "number", "description": "Dung tích hữu ích (triệu m3)", "example": "74.89"},
            "wtb": {"type": "number", "description": "Dung tích toàn bộ (triệu m3)", "example": "89.8"},
            "mndangbt": {"type": "number", "description": "Mực nước dâng bình thường (m)", "example": "101.1"},
            "mndanggiacuong": {"type": "number", "description": "Mực nước dâng gia cường (m)", "example": "102.23"},
            "mnchet": {"type": "number", "description": "Mực nước chết (m)", "example": "77"},
            "ftk": {"type": "number", "description": "Diện tích tưới thiết kế (ha)", "example": "700"},
            "mucnuoc": {"type": "number", "description": "Mực nước (realtime)", "example": "10.4"},
        },
        "required": [],
        "callable": tra_cuu_cong_trinh,
    },
    {
        "name": "hoi_dap_chung",
        "description": "Các câu hỏi chung về thủy lợi, pháp luật, quy trình, khái niệm chuyên ngành.",
        "parameters": {},
        "callable": hoi_dap_chung
    }
]

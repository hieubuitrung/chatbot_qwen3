**Cài thư viện**
Cài tất cả thư viện bằng cú pháp: pip install -r requirements.txt

**Chạy dự án trong môi trường ảo**
Sử dụng câu lệnh: venv\Scripts\activate

# Cài đặt geopandas

conda install geopandas

<!-- thư viện kết nối postgre và python -->

conda install -c conda-forge psycopg2

# Bắt buộc: PyTorch CPU + Transformers

conda install pytorch cpuonly -c pytorch
conda install -c conda-forge transformers

<!-- pip install sentencepiece -->

conda install -c conda-forge accelerate

torch → bắt buộc để load model và chạy inference (câu lệnh trên đang cài bản chạy trên cpu)
transformers → để load model/tokenizer từ HuggingFace

<!-- sentencepiece → cần nếu tokenizer của model dùng SP (đa số LLM nhỏ đều dùng) -->

accelerate → để tự động map model sang CPU/GPU.

# Cài đặt LlamaIndex và Qdrant và mô hình để embedding

<!-- pip install llama-index qdrant-client sentence-transformers -->

<!-- llama-index → một khung điều phối hoặc khung dữ liệu giúp đơn giản hóa việc xây dựng các ứng dụng LLM -->
<!-- qdrant-client → một công cụ mạnh mẽ để tìm kiếm vectơ, tạo, chèn và tìm kiếm vectơ -->
<!-- sentence-transformers → cung cấp các mô hình pre-trained để tạo ra embeddings cho các câu và đoạn văn -->

# Cài đặt công cụ giữa LlamaIndex và Qdrant

<!-- pip install llama-index-vector-stores-qdrant -->

<!-- llama-index-vector-stores-qdrant -> kết nối và tương tác giữa LlamaIndex và cơ sở dữ liệu vector Qdrant -->

#

đoạn code ở demo1 đang thiết vì tôi đã xóa, đang tính chuyển sang SentenceTransformer thay vì dùng HuggingFace
pip install llama-index-embeddings-huggingface

# cài đặt fastapi và uvicorn

conda install -c conda-forge fastapi uvicorn
fastapi -> tạo api
uvicorn -> server để chạy fastapi

# chạy uvicorn - server cho pastAPI

uvicorn app.api:app --reload
!uvicorn app.api:app --host 0.0.0.0 --port 8000

##

# tổng hợp thư viện của project vào file requirements.txt

pip freeze > requirements.txt

# khi chuyển sang máy khác thì cài thư viện trong file requirements.txt

pip install -r requirements.txt

# Minianaconda - sau khi cài xong thì làm các bước sau để tạo môi trường

1.  Chấp nhận điều khoản (ToS): conda tos accept

2.  Tạo môi trường mới (dùng bản 3.10 hoặc 3.11 cho ổn định): conda create -n chatbot_conda python=3.11 -y

3.  Kích hoạt môi trường: conda activate chatbot_conda

# Thoát khỏi môi trường hiện tại

conda deactivate

# Xóa sổ môi trường bị lỗi

conda remove -n chatbot_conda --all -y

# Tạo lại môi trường mới tinh với Python 3.11

conda create -n chatbot_conda python=3.11 -y

# Kích hoạt lại

conda activate chatbot_conda

# Kích hoạt 2 extention trong pg

-- 1. Cho phép xóa dấu tiếng Việt
CREATE EXTENSION IF NOT EXISTS unaccent;

-- 2. Cho phép tìm kiếm theo độ tương đồng (Trigram)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

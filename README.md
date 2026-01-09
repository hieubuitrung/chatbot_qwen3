# Chatbot Quy Hoạch – Hướng dẫn cài đặt & chạy dự án

## 1. Yêu cầu hệ thống

- **Python**: 3.11
- **Miniconda**
- **PostgreSQL**
- **Hệ điều hành**: Windows

---

## 2. Tạo và quản lý môi trường Conda

### 2.1. Chấp nhận điều khoản Conda (chỉ làm 1 lần)

```bash
conda tos accept
```

### 2.2. Tạo môi trường mới

```bash
conda create -n chatbot_conda python=3.11 -y
```

### 2.3. Kích hoạt môi trường

```bash
conda activate chatbot_conda
```

### 2.4. Thoát môi trường

```bash
conda deactivate
```

### 2.5. Xóa môi trường (khi bị lỗi)

```bash
conda remove -n chatbot_conda --all -y
```

---

## 3. Cài đặt thư viện nền tảng

### 3.1. Cài đặt GeoPandas (GIS)

```bash
conda install geopandas
```

### 3.2. Kết nối PostgreSQL với Python

```bash
conda install -c conda-forge psycopg2
```

---

## 4. PyTorch & Transformers (bắt buộc)

> Dùng **CPU** khi thiết bị không hỗ trợ GPU.

```bash
conda install pytorch cpuonly -c pytorch
conda install -c conda-forge transformers
conda install -c conda-forge accelerate
```

**Giải thích:**

- `torch`: load model và chạy inference (CPU)
- `transformers`: load model / tokenizer từ HuggingFace
- `accelerate`: tự động map model sang CPU/GPU

---

## 5. LlamaIndex, Qdrant & Embedding

### 5.1. Thư viện chính

```bash
pip install llama-index qdrant-client sentence-transformers
```

**Mô tả:**

- `llama-index`: framework điều phối dữ liệu cho ứng dụng LLM
- `qdrant-client`: cơ sở dữ liệu vector
- `sentence-transformers`: tạo embedding cho câu và đoạn văn

### 5.2. Kết nối LlamaIndex với Qdrant

```bash
pip install llama-index-vector-stores-qdrant
```

---

## 6. Embedding Model

```bash
pip install llama-index-embeddings-huggingface
```

---

## 7. FastAPI & Uvicorn

### 7.1. Cài đặt

```bash
conda install -c conda-forge fastapi uvicorn
```

**Giải thích:**

- `fastapi`: xây dựng REST API
- `uvicorn`: ASGI server để chạy FastAPI

### 7.2. Chạy server

```bash
uvicorn app.api:app --reload
```

Hoặc chạy public IP:

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

---

## 8. Quản lý thư viện với Conda

### 8.1. Xuất danh sách thư viện ra environment.yml

```bash
conda env export --no-builds > environment.yml
```

> File `environment.yml` sẽ bao gồm:
>
> - Phiên bản Python
> - Danh sách thư viện Conda
> - Các gói cài bằng `pip`

### 8.2. Cài lại môi trường trên máy khác từ environment.yml

```bash
conda env create -f environment.yml
```

Sau đó kích hoạt môi trường:

```bash
conda activate chatbot_conda
```

---

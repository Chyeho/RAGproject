'''配置文件'''

md5_path = "./md5.txt"

# Chroma
collection_name = "rag"
persist_directory = "./chroma_db"

# spliter
chunk_size = 1000
chunk_overlap = 100
separators = ["\n\n","\n","。","!","！","?","？","."," ",""]
max_split_char_number = 1000

# vector_store
similarity_threshold = 1
embedding_model_name = "text-embedding-v4"
chat_model_name = "deepseek-v4-pro"

# session id 配置
session_config = {
    "configurable":{
        "session_id":"user_001",
    }
}
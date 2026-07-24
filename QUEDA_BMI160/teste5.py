import os
import glob
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Adicione estas importações no topo do seu arquivo .py
from sklearn.ensemble import RandomForestClassifier
from micromlgen import port


def extract_fs1_features(df, x_col, y_col, z_col):
    """
    Extrai o conjunto de características FS-1 (máximo, mínimo, média e variância)
    para cada eixo do acelerômetro.
    """
    features = []
    for col in [x_col, y_col, z_col]:
        features.extend([
            df[col].max(),
            df[col].min(),
            df[col].mean(),
            df[col].var()
        ])
    return features

def load_and_preprocess_dataset(base_path):
    """
    Percorre a estrutura de diretórios do WEDA-FALL e compila as características e rótulos,
    filtrando apenas os arquivos do acelerômetro.
    """
    X = [] # Matriz de características
    y = [] # Vetor de rótulos (1 para Queda, 0 para ADL)
    
    # Percorre todas as pastas no diretório base (ex: F01, D03, etc.)
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        # F01 a F08 representam quedas (1), D01 a D11 representam ADLs (0)
        is_fall = 1 if folder_name.startswith('F') else 0
        
        # Lê todos os arquivos CSV na pasta
        csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
        
        # Filtra para manter apenas os arquivos de acelerômetro (ignora gyro e orientation)
        accel_files = [f for f in csv_files if 'accel.csv' in f.lower()]
        
        for file_path in accel_files:
            try:
                df = pd.read_csv(file_path)
                
                # Identifica e mapeia as colunas dependendo da estrutura do arquivo
                if 'accel_x_list' in df.columns:
                    x_col, y_col, z_col = 'accel_x_list', 'accel_y_list', 'accel_z_list'
                elif 'vertical_Accel_x' in df.columns:
                    x_col, y_col, z_col = 'vertical_Accel_x', 'vertical_Accel_y', 'vertical_Accel_z'
                else:
                    # Este print não deve mais aparecer, mas é mantido por segurança
                    print(f"Colunas não reconhecidas no arquivo: {file_path}")
                    continue
                
                # Ignora arquivos vazios ou com dados insuficientes para variância
                if len(df) < 2:
                    continue
                    
                # Extrai as 12 características (4 de cada eixo)
                features = extract_fs1_features(df, x_col, y_col, z_col)
                
                X.append(features)
                y.append(is_fall)
                
            except Exception as e:
                print(f"Erro ao processar {file_path}: {e}")
                
    return np.array(X), np.array(y)

# ==========================================
# Execução Principal (Treino e Exportação)
# ==========================================

DATASET_PATH = 'dataset/50Hz/'

print("Carregando dados e extraindo características...")
X, y = load_and_preprocess_dataset(DATASET_PATH)

# Divide os dados em treino (80%) e teste (20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# Instancia e treina o algoritmo Decision Tree
print("\nTreinando o modelo Random Forest...")

# É crucial limitar n_estimators e max_depth para embarcados.
# Comece com valores baixos e aumente conforme a memória da placa permitir.
rf_model = RandomForestClassifier(n_estimators=15, max_depth=15, random_state=42, class_weight='balanced') 
rf_model.fit(X_train, y_train)

y_pred = rf_model.predict(X_test)

print("\nResultados da Avaliação (Random Forest):")
print("-" * 30)
print(f"Acurácia: {accuracy_score(y_test, y_pred):.4f}")
print(classification_report(y_test, y_pred, target_names=['ADL (0)', 'Queda (1)']))

print("\nExportando modelo para C++...")
c_code = port(rf_model)

# Salve o modelo em um novo arquivo
with open("rf_model.h", "w") as file:
    file.write(c_code)

print("Modelo exportado com sucesso para rf_model.h!")
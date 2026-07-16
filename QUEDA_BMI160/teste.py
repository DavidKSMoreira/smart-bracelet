import os
import glob
import pandas as pd
import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

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
# Execução Principal
# ==========================================

DATASET_PATH = 'dataset/50Hz/'

print("Carregando dados e extraindo características...")
X, y = load_and_preprocess_dataset(DATASET_PATH)

if len(X) == 0:
    print("Nenhum dado encontrado. Verifique o caminho do diretório.")
else:
    print(f"Total de amostras processadas: {len(X)}")
    print(f"Quedas detectadas no dataset: {sum(y)}")
    print(f"ADLs detectadas no dataset: {len(y) - sum(y)}")
    
    # Divide os dados em treino (80%) e teste (20%)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # Instancia e treina o algoritmo 3-Nearest Neighbours (3NN) com distância Euclidiana
    print("\nTreinando o modelo 3NN...")
    knn_model = KNeighborsClassifier(n_neighbors=3, metric='euclidean')
    knn_model.fit(X_train, y_train)
    
    
    # Realiza as predições e avalia o modelo
    y_pred = knn_model.predict(X_test)
    
    print("\nResultados da Avaliação:")
    print("-" * 30)
    print(f"Acurácia: {accuracy_score(y_test, y_pred):.4f}")
    print("\nRelatório de Classificação:")
    print(classification_report(y_test, y_pred, target_names=['ADL (0)', 'Queda (1)']))
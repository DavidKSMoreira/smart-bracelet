import os
import glob
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.neighbors import KNeighborsClassifier # Modificação 1: Importar KNN

def extract_fs1_features(df, x_col, y_col, z_col):
    """
    Extrai o conjunto de características FS-1 (máximo, mínimo, média e variância)
    para cada eixo do acelerômetro, SEM o Vetor de Magnitude do Sinal (SMV).
    """
    features = []
    
    # Modificação 2: Extrai as 4 características APENAS para os eixos X, Y e Z (Total: 12 features)
    for col in [x_col, y_col, z_col]:
        features.extend([
            df[col].max(),
            df[col].min(),
            df[col].mean(),
            df[col].var(ddof=1) # ddof=1 garante a variância amostral
        ])
        
    return features

def load_and_preprocess_dataset(base_path):
    """
    Percorre a estrutura de diretórios do WEDA-FALL e compila as características e rótulos,
    filtrando apenas os arquivos do acelerômetro.
    """
    X = [] # Matriz de características
    y = [] # Vetor de rótulos (1 para Queda, 0 para ADL)
    
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        is_fall = 1 if folder_name.startswith('F') else 0
        csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
        accel_files = [f for f in csv_files if 'accel.csv' in f.lower()]
        
        for file_path in accel_files:
            try:
                df = pd.read_csv(file_path)
                
                if 'accel_x_list' in df.columns:
                    x_col, y_col, z_col = 'accel_x_list', 'accel_y_list', 'accel_z_list'
                elif 'vertical_Accel_x' in df.columns:
                    x_col, y_col, z_col = 'vertical_Accel_x', 'vertical_Accel_y', 'vertical_Accel_z'
                else:
                    print(f"Colunas não reconhecidas no arquivo: {file_path}")
                    continue
                
                if len(df) < 2:
                    continue
                    
                # Extrai agora 12 características (4 de X, 4 de Y, 4 de Z)
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

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

print("\nTreinando o modelo K-Nearest Neighbours (3NN)...")
# Modificação 3: Substituição da Árvore de Decisão pelo 3NN com distância Euclidiana
knn_model = KNeighborsClassifier(n_neighbors=3, metric='euclidean') 
knn_model.fit(X_train, y_train)

y_pred = knn_model.predict(X_test)

print("\nResultados da Avaliação (3NN):")
print("-" * 30)
print(f"Acurácia: {accuracy_score(y_test, y_pred):.4f}")
print("\nRelatório de Classificação:")
print(classification_report(y_test, y_pred, target_names=['ADL (0)', 'Queda (1)']))

clf = knn_model

# ==========================================
# Validação da Queda Simulada
# ==========================================

print("\nValidando arquivo de simulação...")
df_simulacao = pd.read_csv('queda_simulada.csv', names=['X', 'Y', 'Z'])

# Modificação 4: Janela de 9 segundos (450 amostras a 50Hz) sem sobreposição
window_size = 450
step_size = 450 

# Processa os dados em janelas sequenciais de 9 segundos
for i in range(0, len(df_simulacao) - window_size + 1, step_size):
    window = df_simulacao.iloc[i:i+window_size]
        
    features = []
    
    # Extrai as 4 características para os eixos X, Y e Z (Total 12 features)
    for axis in ['X', 'Y', 'Z']:
        features.extend([
            window[axis].max(),
            window[axis].min(),
            window[axis].mean(),
            window[axis].var(ddof=1)
        ])
        
    X_test_simulacao = np.array([features])
    
    prediction = clf.predict(X_test_simulacao)
    resultado = "QUEDA" if prediction[0] == 1 else "ADL"
    
    # Exibe o intervalo de amostras avaliado
    print(f"Amostras {i} a {i+window_size-1}: Classificação = {resultado}")
    print(f"   -> Primeira feature (Max_X) = {features[0]:.2f}")
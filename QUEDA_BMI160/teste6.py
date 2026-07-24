import os
import glob
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.tree import DecisionTreeClassifier
from micromlgen import port

def extract_all_metrics_features(df_accel, df_va):
    """
    Extrai as características (Média e Máximo) para TA, VA, TV, VV, TD e VD,
    conforme as integrações temporais descritas no artigo.
    """
    # 1. Calcula TA (Total Acceleration) removendo a gravidade (aprox. 9.81 m/s^2)
    accel_mag = np.sqrt(df_accel['accel_x_list']**2 + 
                        df_accel['accel_y_list']**2 + 
                        df_accel['accel_z_list']**2)
    TA = np.abs(accel_mag - 9.81)
    
    # 2. Calcula VA (Vertical Acceleration) usando o arquivo com os componentes verticais
    VA = np.sqrt(df_va['vertical_Accel_x']**2 + 
                 df_va['vertical_Accel_y']**2 + 
                 df_va['vertical_Accel_z']**2)
    
    # Define o delta de tempo (dt) para as integrações
    if 'accel_time_list' in df_accel.columns:
        dt = df_accel['accel_time_list'].diff().fillna(0).values
    else:
        dt = 0.02  # Fallback para 50Hz
        
    # 3. Calcula TV (Total Velocity) por integração no tempo de TA
    TV = np.cumsum(TA * dt)
    
    # 4. Calcula VV (Vertical Velocity) por integração no tempo de VA
    VV = np.cumsum(VA * dt)
    
    # 5. Calcula TD (Total Displacement) por integração no tempo de TV
    TD = np.cumsum(TV * dt)
    
    # 6. Calcula VD (Vertical Displacement) por integração no tempo de VV
    VD = np.cumsum(VV * dt)
    
    # 7. Extrai as características selecionadas (Média e Máximo de cada sinal)
    features = [
        TA.mean(), TA.max(),
        #VA.mean(), VA.max(),
        TV.mean(), TV.max(),
        VV.mean(), VV.max(),
        #TD.mean(), TD.max(),
        VD.mean(), VD.max()
    ]
    
    return features

def load_and_preprocess_dataset(base_path):
    """
    Percorre a estrutura de diretórios e compila as características baseadas
    nas 6 métricas propostas no artigo.
    """
    X = [] # Matriz de características
    y = [] # Vetor de rótulos (1 para Queda, 0 para ADL)
    
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        is_fall = 1 if folder_name.startswith('F') else 0
        
        # Encontra todos os arquivos accel e filtra os que não são verticais para encontrar o par correto
        accel_files = glob.glob(os.path.join(folder_path, '*_accel.csv'))
        regular_accel_files = [f for f in accel_files if 'vertical' not in f.lower()]
        
        for accel_file in regular_accel_files:
            try:
                # Localiza o arquivo vertical equivalente
                base_name = accel_file.replace('_accel.csv', '')
                va_file = base_name + '_vertical_accel.csv'
                
                if not os.path.exists(va_file):
                    #print(f"Arquivo vertical não encontrado para: {accel_file}")
                    continue
                
                df_accel = pd.read_csv(accel_file)
                df_va = pd.read_csv(va_file)
                
                if len(df_accel) < 2 or len(df_va) < 2:
                    continue
                    
                # Extrai as 12 features (Média e Max de TA, VA, TV, VV, TD, VD)
                features = extract_all_metrics_features(df_accel, df_va)
                
                X.append(features)
                y.append(is_fall)
                
            except Exception as e:
                print(f"Erro ao processar par {accel_file}: {e}")
                
    return np.array(X), np.array(y)

# ==========================================
# Execução Principal (Treino e Avaliação)
# ==========================================

DATASET_PATH = 'dataset/50Hz/'

print("Carregando dados e extraindo as 12 características (TA, VA, TV, VV, TD, VD)...")
X, y = load_and_preprocess_dataset(DATASET_PATH)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

print("\nTreinando o modelo Decision Tree...")
dt_model = DecisionTreeClassifier(max_depth=10, class_weight='balanced', random_state=42) 
dt_model.fit(X_train, y_train)

y_pred = dt_model.predict(X_test)

print("\nResultados da Avaliação (Decision Tree):")
print("-" * 30)
print(f"Acurácia: {accuracy_score(y_test, y_pred):.4f}")
print("\nRelatório de Classificação:")
print(classification_report(y_test, y_pred, target_names=['ADL (0)', 'Queda (1)']))

print("\nExportando modelo para C++...")
c_code = port(dt_model)

# Salve o modelo em um novo arquivo
with open("dt_model.h", "w") as file:
    file.write(c_code)

print("Modelo exportado com sucesso para dt_model.h!")
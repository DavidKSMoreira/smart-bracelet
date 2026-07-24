import os
import glob
import itertools
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.tree import DecisionTreeClassifier
from micromlgen import port

def extract_all_metrics_features(df_accel, df_va):
    """
    Extrai as características (Média e Máximo) para TA, VA, TV, VV, TD e VD.
    """
    # 1. Calcula TA (Total Acceleration) removendo a gravidade (aprox. 9.81 m/s^2)
    accel_mag = np.sqrt(df_accel['accel_x_list']**2 + 
                        df_accel['accel_y_list']**2 + 
                        df_accel['accel_z_list']**2)
    TA = np.abs(accel_mag - 9.81)
    
    # 2. Calcula VA (Vertical Acceleration)
    VA = np.sqrt(df_va['vertical_Accel_x']**2 + 
                 df_va['vertical_Accel_y']**2 + 
                 df_va['vertical_Accel_z']**2)
    
    # Define o delta de tempo (dt) para as integrações
    if 'accel_time_list' in df_accel.columns:
        dt = df_accel['accel_time_list'].diff().fillna(0).values
    else:
        dt = 0.02  # Fallback para 50Hz
        
    # Integrações
    TV = np.cumsum(TA * dt)
    VV = np.cumsum(VA * dt)
    TD = np.cumsum(TV * dt)
    VD = np.cumsum(VV * dt)
    
    # Média e Máximo de cada sinal
    features = [
        TA.mean(), TA.max(), # Índices 0, 1
        VA.mean(), VA.max(), # Índices 2, 3
        TV.mean(), TV.max(), # Índices 4, 5
        VV.mean(), VV.max(), # Índices 6, 7
        TD.mean(), TD.max(), # Índices 8, 9
        VD.mean(), VD.max()  # Índices 10, 11
    ]
    
    return features

def load_and_preprocess_dataset(base_path):
    X = [] 
    y = [] 
    
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        is_fall = 1 if folder_name.startswith('F') else 0
        
        accel_files = glob.glob(os.path.join(folder_path, '*_accel.csv'))
        regular_accel_files = [f for f in accel_files if 'vertical' not in f.lower()]
        
        for accel_file in regular_accel_files:
            try:
                base_name = accel_file.replace('_accel.csv', '')
                va_file = base_name + '_vertical_accel.csv'
                
                if not os.path.exists(va_file):
                    continue
                
                df_accel = pd.read_csv(accel_file)
                df_va = pd.read_csv(va_file)
                
                if len(df_accel) < 2 or len(df_va) < 2:
                    continue
                    
                features = extract_all_metrics_features(df_accel, df_va)
                X.append(features)
                y.append(is_fall)
                
            except Exception as e:
                pass
                
    return np.array(X), np.array(y)

# ==========================================
# 1. Carregamento e Avaliação das Combinações
# ==========================================

DATASET_PATH = 'dataset/50Hz/'

print("Carregando dados e extraindo as 12 características (TA, VA, TV, VV, TD, VD)...")
X, y = load_and_preprocess_dataset(DATASET_PATH)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

signal_indices = {
    'TA': [0, 1], 'VA': [2, 3], 'TV': [4, 5],
    'VV': [6, 7], 'TD': [8, 9], 'VD': [10, 11]
}

signals = list(signal_indices.keys())
all_combinations = []

for r in range(1, len(signals) + 1):
    all_combinations.extend(itertools.combinations(signals, r))

results = []
print(f"\nAvaliando {len(all_combinations)} combinações...\n")

for combo in all_combinations:
    selected_cols = []
    for sig in combo:
        selected_cols.extend(signal_indices[sig])
        
    X_train_sub = X_train[:, selected_cols]
    X_test_sub = X_test[:, selected_cols]
    
    dt_model = DecisionTreeClassifier(max_depth=10, class_weight='balanced', random_state=42)
    dt_model.fit(X_train_sub, y_train)
    
    y_pred = dt_model.predict(X_test_sub)
    acc = accuracy_score(y_test, y_pred)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    
    results.append({
        'Combinação': ", ".join(combo),
        'Acurácia': acc,
        'Sensibilidade': sensitivity,
        'Especificidade': specificity
    })

df_results = pd.DataFrame(results)
df_results_sorted = df_results.sort_values(by=['Acurácia', 'Sensibilidade', 'Especificidade'], ascending=[False, False, False]).reset_index(drop=True)

melhor_combo = df_results_sorted.iloc[0]
print("=" * 60)
print(f"🏆 MELHOR COMBINAÇÃO: [{melhor_combo['Combinação']}]")
print(f"   Acurácia:       {melhor_combo['Acurácia']:.4f}")
print(f"   Sensibilidade:  {melhor_combo['Sensibilidade']:.4f}")
print(f"   Especificidade: {melhor_combo['Especificidade']:.4f}")
print("=" * 60)

# ==========================================
# 2. Treinamento Final e Exportação (.h)
# ==========================================

print("\nTreinando modelo final com a melhor combinação...")

# Extrai os nomes dos sinais da melhor combinação (ex: 'VA, TV' -> ['VA', 'TV'])
melhores_sinais = melhor_combo['Combinação'].split(", ")

# Coleta os índices correspondentes à melhor combinação
best_columns = []
for sig in melhores_sinais:
    best_columns.extend(signal_indices[sig])

# Filtra o dataset completo apenas com as features vencedoras
X_best = X[:, best_columns]

# Treina a árvore de decisão final usando todo o dataset para máxima captura de padrões
clf_final = DecisionTreeClassifier(max_depth=10, class_weight='balanced', random_state=42)
clf_final.fit(X_best, y)

print("Exportando modelo para C/C++...")

# Mapeia as saídas para nomes claros no código C
class_map = {0: 'ADL', 1: 'QUEDA'}

# O método port() converte a árvore em puro código C
c_code = port(clf_final, classmap=class_map)

with open('modelo_queda.h', 'w') as f:
    f.write(c_code)

print("\nConcluído! O arquivo 'modelo_queda.h' foi gerado no seu diretório.")
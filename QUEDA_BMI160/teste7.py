import os
import glob
import itertools
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.tree import DecisionTreeClassifier



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
        TA.mean(), TA.max(), # Índices 0, 1
        VA.mean(), VA.max(), # Índices 2, 3
        TV.mean(), TV.max(), # Índices 4, 5
        VV.mean(), VV.max(), # Índices 6, 7
        TD.mean(), TD.max(), # Índices 8, 9
        VD.mean(), VD.max()  # Índices 10, 11
    ]
    
    return features

def load_and_preprocess_dataset(base_path):
    """
    Percorre a estrutura de diretórios e compila as características baseadas
    nas 6 métricas propostas no artigo.
    """
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
                print(f"Erro ao processar par {accel_file}: {e}")
                
    return np.array(X), np.array(y)

# ==========================================
# Execução Principal (Treino e Avaliação Múltipla)
# ==========================================

DATASET_PATH = 'dataset/50Hz/'

print("Carregando dados e extraindo as 12 características (TA, VA, TV, VV, TD, VD)...")
X, y = load_and_preprocess_dataset(DATASET_PATH)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# Mapeamento de sinais para os respectivos índices das colunas geradas em 'extract_all_metrics_features'
signal_indices = {
    'TA': [0, 1],
    'VA': [2, 3],
    'TV': [4, 5],
    'VV': [6, 7],
    'TD': [8, 9],
    'VD': [10, 11]
}

signals = list(signal_indices.keys())
all_combinations = []

# Gera todas as combinações possíveis (tamanhos de 1 a 6)
for r in range(1, len(signals) + 1):
    all_combinations.extend(itertools.combinations(signals, r))

results = []

print(f"\nIniciando testes para {len(all_combinations)} combinações de sinais...\n")

for combo in all_combinations:
    # Coleta os índices das features para a combinação atual
    selected_cols = []
    for sig in combo:
        selected_cols.extend(signal_indices[sig])
        
    X_train_sub = X_train[:, selected_cols]
    X_test_sub = X_test[:, selected_cols]
    
    # Treina o modelo Decision Tree
    dt_model = DecisionTreeClassifier(max_depth=10, class_weight='balanced', random_state=42)
    dt_model.fit(X_train_sub, y_train)
    
    # Predição e métricas
    y_pred = dt_model.predict(X_test_sub)
    acc = accuracy_score(y_test, y_pred)
    
    # Obtém a matriz de confusão para calcular Sensibilidade e Especificidade
    # tn: True Negatives (ADL classificado como ADL)
    # fp: False Positives (ADL classificado como Queda)
    # fn: False Negatives (Queda classificada como ADL)
    # tp: True Positives (Queda classificada como Queda)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    
    results.append({
        'Combinação': ", ".join(combo),
        'Qtd_Sinais': len(combo),
        'Acurácia': acc,
        'Sensibilidade': sensitivity,
        'Especificidade': specificity
    })

# Converte os resultados para um DataFrame para facilitar a ordenação e visualização
df_results = pd.DataFrame(results)

# Ordena pelos melhores resultados (Prioridade: Acurácia > Sensibilidade > Especificidade)
df_results_sorted = df_results.sort_values(by=['Acurácia', 'Sensibilidade', 'Especificidade'], ascending=[False, False, False]).reset_index(drop=True)

# Exibe o Top 10 das melhores combinações
print("=" * 70)
print("TOP 10 MELHORES COMBINAÇÕES DE SINAIS (DECISION TREE)")
print("=" * 70)
print(df_results_sorted.head(10).to_string(index=False, formatters={
    'Acurácia': '{:.4f}'.format,
    'Sensibilidade': '{:.4f}'.format,
    'Especificidade': '{:.4f}'.format
}))

print("\n" + "=" * 70)
melhor_combo = df_results_sorted.iloc[0]
print(f"🏆 A MELHOR COMBINAÇÃO ENCONTRADA FOI: [{melhor_combo['Combinação']}]")
print(f"   Acurácia:       {melhor_combo['Acurácia']:.4f}")
print(f"   Sensibilidade:  {melhor_combo['Sensibilidade']:.4f}")
print(f"   Especificidade: {melhor_combo['Especificidade']:.4f}")
print("=" * 70)
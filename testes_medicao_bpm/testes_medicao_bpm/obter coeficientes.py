from scipy import signal

def generate_coefficients(low, high, fs, order=2):
    # 'order=2' para passa-banda gera um filtro de 4ª ordem (10 coeficientes)
    nyq = 0.5 * fs
    low_norm = low / nyq
    high_norm = high / nyq
    
    b, a = signal.butter(order, [low_norm, high_norm], btype='band', analog=False)
    
    print(f"// Fs = {fs}Hz, Band = {low}-{high}Hz")
    print(f"double b[] = {{{', '.join([f'{x:.10f}' for x in b])}}};")
    print(f"double a[] = {{{', '.join([f'{x:.10f}' for x in a])}}};")

generate_coefficients(0.6666667, 3.66666667, 100.0)
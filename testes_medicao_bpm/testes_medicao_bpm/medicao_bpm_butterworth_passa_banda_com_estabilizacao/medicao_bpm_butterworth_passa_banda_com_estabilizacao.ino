#include <Wire.h>
#include "MAX30105.h"
#include "arduinoFFT.h"

MAX30105 particleSensor;

#define PULSE_SAMPLES 512
#define SAMPLE_FREQ 100.0 

// Estrutura do Filtro Butterworth
typedef struct {
    double x[5]; 
    double y[5]; 
    double a[5]; 
    double b[5]; 
} ButterworthBP;

// Instância GLOBAL do filtro
ButterworthBP meuFiltro = {
    {0,0,0,0,0}, {0,0,0,0,0},
    {1.0000000000, -3.7166661880, 5.2016838260, -3.2509423838, 0.7660066030},
    {0.0078202079, 0.0000000000, -0.0156404158, 0.0000000000, 0.0078202079}
};

double vReal[PULSE_SAMPLES];
double vImag[PULSE_SAMPLES];
int sampleIndex = 0;

// Variável para a estabilização (Média Móvel Exponencial)
double lastStabilized = 0; 
const double STABILIZATION_TIME = 1.0; // 1 segundo
const double N = SAMPLE_FREQ * STABILIZATION_TIME; 

ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal, vImag, PULSE_SAMPLES, SAMPLE_FREQ);

// Filtro passa banda butterworth
double process_filter(ButterworthBP *f, double x) {
    for (int i = 4; i > 0; i--) {
        f->x[i] = f->x[i - 1];
        f->y[i] = f->y[i - 1];
    }
    f->x[0] = x;
    f->y[0] = (f->b[0] * f->x[0]) + (f->b[1] * f->x[1]) + (f->b[2] * f->x[2]) + (f->b[3] * f->x[3]) + (f->b[4] * f->x[4])
              - (f->a[1] * f->y[1]) - (f->a[2] * f->y[2]) - (f->a[3] * f->y[3]) - (f->a[4] * f->y[4]);
    return f->y[0];
}

void setup() {
    Serial.begin(115200);
    if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println("MAX30102 não encontrado!");
        while (1);
    }

    byte ledBrightness = 0xC8;
    byte sampleAverage = 1;   
    byte ledMode = 2; 
    int sampleRate = 100; // Ajustado para 100Hz conforme seu código
    int pulseWidth = 411; 
    int adcRange = 16384; 
    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);
}

void loop() {
    particleSensor.check(); 

    while (particleSensor.available()) {
        double rawData = (double)particleSensor.getFIFOIR(); 
        
        // 1. Passo: Filtro Butterworth (Frequência)
        double butterData = process_filter(&meuFiltro, rawData);
        
        // 2. Passo: Estabilização (Remoção de oscilações bruscas)
        // Fórmula: (Valor_Anterior * N + Valor_Atual) / (N + 1)
        double stabilizedData = (lastStabilized * N + butterData) / (N + 1.0);
        lastStabilized = stabilizedData; // Salva para a próxima iteração

        // Armazena para FFT
        vReal[sampleIndex] = stabilizedData;
        vImag[sampleIndex] = 0.0;
        
        // Visualização no Serial Plotter
        Serial.println(vReal[sampleIndex]);
        
        sampleIndex++;
        particleSensor.nextSample();
        
        if (sampleIndex >= PULSE_SAMPLES) {
            FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD);
            FFT.compute(FFT_FORWARD);
            FFT.complexToMagnitude();

            double peakHz = FFT.majorPeak();
            double bpm = peakHz * 60.0;

            //Serial.print("BPM: ");
            //Serial.println(bpm);

            sampleIndex = 0; 
        }
    }
}

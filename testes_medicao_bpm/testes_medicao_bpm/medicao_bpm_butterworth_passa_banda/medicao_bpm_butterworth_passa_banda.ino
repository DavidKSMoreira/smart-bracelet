#include <Wire.h>
#include "MAX30105.h"
#include "arduinoFFT.h"

MAX30105 particleSensor;

#define PULSE_SAMPLES 256
#define SAMPLE_FREQ 50.0 // Mantemos 50Hz para casar com os coeficientes

// Estrutura do Filtro
typedef struct {
    double x[5]; 
    double y[5]; 
    double a[5]; 
    double b[5]; 
} ButterworthBP;

// Instância GLOBAL para não perder o histórico (CORREÇÃO 1)
ButterworthBP meuFiltro = {
    {0,0,0,0,0}, {0,0,0,0,0},
    {1.0, -3.4078144290, 4.4197941897, -2.5977384289, 0.5869195112},
    {0.0278597656, 0.0, -0.0557195312, 0.0, 0.0278597656}
};

double vReal[PULSE_SAMPLES];
double vImag[PULSE_SAMPLES];
int sampleIndex = 0;

ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal, vImag, PULSE_SAMPLES, SAMPLE_FREQ);

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

    // CONFIGURAÇÃO PARA 50Hz EFETIVOS (CORREÇÃO 2)
    byte ledBrightness = 0x7F;
    byte sampleAverage = 1;   // Sem média para manter 50Hz puro
    byte ledMode = 2; 
    int sampleRate = 50;      // 50Hz direto
    int pulseWidth = 411; 
    int adcRange = 16384; 
    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);
}

void loop() {
    particleSensor.check(); 

    while (particleSensor.available()) {
        // No MAX30102, às vezes as funções Red/IR são trocadas dependendo do fabricante do módulo
        double rawData = (double)particleSensor.getFIFOIR(); 
        
        // Filtra a amostra IMEDIATAMENTE antes de guardar (Melhor estabilidade)
        vReal[sampleIndex] = process_filter(&meuFiltro, rawData);
        vImag[sampleIndex] = 0.0;
        
        sampleIndex++;
        particleSensor.nextSample();
        Serial.println(vReal[sampleIndex-1]);

        if (sampleIndex >= PULSE_SAMPLES) {
            // Executa a FFT
            FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD);
            FFT.compute(FFT_FORWARD);
            FFT.complexToMagnitude();

            double peakHz = FFT.majorPeak();
            double bpm = peakHz * 60.0;

            //Serial.print("BPM: ");
            //Serial.println(bpm);

            sampleIndex = 0; // Reinicia a coleta para o próximo bloco
        }
    }
}

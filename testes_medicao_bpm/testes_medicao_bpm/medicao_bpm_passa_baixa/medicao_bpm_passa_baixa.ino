// Tinker Foundry
// Heart Rate Measurement with the MAX30102 breakout board using FFT
// Connections from WEMOS D1 R32 board to MAX30102 Breakout Board as follows:
//  SCL (ESP32) to SCL (breakout board)
//  SDA (ESP32) to SDA (breakout board)
//  3V3 (ESP32) to VIN (breakout board)
//  GND (ESP32) to GND (breakout board)

#include <Wire.h>
#include "MAX30105.h"    // sparkfun MAX3010X library
MAX30105 particleSensor;

#include "arduinoFFT.h"


double avered       = 0; 
double aveir        = 0;
double sumirrms     = 0;
double sumredrms    = 0;
int    i            = 0;
int    Num          = 100;  // calculate SpO2 by this sampling interval
int    Temperature;
int    temp;
float  ESpO2;               // initial value of estimated SpO2
double FSpO2        = 0.7;  // filter factor for estimated SpO2
double frate        = 0.95; // low pass filter for IR/red LED value to eliminate AC component
#define TIMETOBOOT    3000  // wait for this time(msec) to output SpO2
#define SCALE         88.0  // adjust to display heart beat and SpO2 in the same scale
#define SAMPLING      100   //25 //5     // if you want to see heart beat more precisely, set SAMPLING to 1
#define FINGER_ON     30000 // if red signal is lower than this, it indicates your finger is not on the sensor
#define USEFIFO
#define PULSE_SAMPLES 256
#define SAMPLE_FREQ 50.0

// --- For Heart Rate ---
byte   rateSpot         = 0;
long   lastBeat         = 0;  // Time at which the last beat occurred
int    beatAvg          = 0;
bool   detect_high      = 0;
// ----------------------

double redArray[PULSE_SAMPLES]; // array to store samples from the sensor
double filtered_data[PULSE_SAMPLES];
double vReal[PULSE_SAMPLES];
double vImag[PULSE_SAMPLES];
double beatsPerMinute = 0;

ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal,vImag, PULSE_SAMPLES, SAMPLE_FREQ);

double resposta_anterior = 0;

void filtro_passa_baixa(double* amostras,int qtd_amostras,double alpha, double* dados_filtrados){
    for(int i=0; i<qtd_amostras; i++){
      dados_filtrados[i] = alpha*amostras[i] + (1-alpha)*resposta_anterior;
      resposta_anterior = dados_filtrados[i];
      }
  }


void setup()
{
   Serial.begin(115200);
   Serial.setDebugOutput(true);
   Serial.println();

   Serial.println("Running...");
   delay(3000);

   // Initialize sensor
   while (!particleSensor.begin(Wire, I2C_SPEED_FAST)) //Use default I2C port, 400kHz speed
   {
      Serial.println("MAX30102 was not found. Please check wiring/power/solder jumper at MH-ET LIVE MAX30102 board. ");
      //while (1);
   }

   //Setup to sense a nice looking saw tooth on the plotter
   byte ledBrightness = 0x7F;  // Options: 0=Off to 255=50mA
   byte sampleAverage = 2;     // Options: 1, 2, 4, 8, 16, 32
   byte ledMode       = 2;     // Options: 1 = Red only, 2 = Red + IR, 3 = Red + IR + Green
   //Options: 1 = IR only, 2 = Red + IR on MH-ET LIVE MAX30102 board
   int sampleRate     = 200;   // Options: 50, 100, 200, 400, 800, 1000, 1600, 3200
   int pulseWidth     = 411;   // Options: 69, 118, 215, 411
   int adcRange       = 16384; // Options: 2048, 4096, 8192, 16384
  
   // Set up the wanted parameters
   particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange); //Configure sensor with these settings
   particleSensor.enableDIETEMPRDY();
}

void loop()
{
   uint32_t ir, red, green;
   double fred, fir;
   double SpO2 = 0; //raw SpO2 before low pass filtered
   float red_beat = 0;
   
   particleSensor.check();               // Check the sensor, read up to 3 samples

   while (particleSensor.available()) 
   {  // Do we have new data

      red = particleSensor.getFIFOIR();  // why getFOFOIR output Red data by MAX30102 on MH-ET LIVE breakout board
      ir  = particleSensor.getFIFORed(); // why getFIFORed output IR data by MAX30102 on MH-ET LIVE breakout board

      i++;
      i = i % PULSE_SAMPLES; // wrap around every 256 samples
      fred = (double)red;

      redArray[i] = fred; // populate the array

      particleSensor.nextSample(); // We're finished with this sample so move to next sample

      if (i == 0) // execute every PULSE_SAMPLES
      {
//         Serial.print("Time: ");
//         Serial.println(millis()); // can use this to determine time it takes to collect 256 samples (sample rate)
        
        filtro_passa_baixa(&redArray[0], PULSE_SAMPLES, 0.10, &filtered_data[0]);
        
         for (int idx=0; idx < PULSE_SAMPLES; idx++)
         {
            vReal[idx] = filtered_data[idx];
            vImag[idx] = 0.0;

            Serial.println(filtered_data[idx]);
         }

         //FFT = ArduinoFFT(vReal, vImag, PULSE_SAMPLES, SAMPLE_FREQ); /* Create FFT object */
         FFT.windowing(FFT_WIN_TYP_HAMMING, FFT_FORWARD); /* Weigh data */
         FFT.compute(FFT_FORWARD); /* Compute FFT */
         FFT.complexToMagnitude(); /* Compute magnitudes */

         double peak = FFT.majorPeak();
         //Serial.println(peak, 6);

         // print in beats per minute
         beatsPerMinute = peak * 60;
//         Serial.print("BPM: ");
//         Serial.println(beatsPerMinute);

      }

  }

  //Serial.println(i);
}

#include <BMI160Gen.h>            //https://github.com/hanyazou/BMI160-Arduino
#include <Wire.h>
#include <math.h>
 
// I2C Configuration for ESP32
const int i2c_addr = 0x68;  // Default I2C address for BMI160
const int sda_pin = 8;     // I2C SDA Pin for ESP32 (default GPIO 21)
const int scl_pin = 9;     // I2C SCL Pin for ESP32 (default GPIO 22)
double absolute_accel = 0;
bool queda_livre=false;
bool impacto=false;
bool imobilidade=true;

void setup() {
  // Initialize Serial communication at 115200 baud rate

  pinMode(1,OUTPUT);
  pinMode(2,INPUT_PULLDOWN);

  Serial.begin(115200);
  while (!Serial); // Wait for Serial Monitor to connect (not required on ESP32)
 
  // Initialize I2C with custom SDA and SCL pins
  Wire.begin(sda_pin, scl_pin);
 
  // Initialize the BMI160 device in I2C mode
  if (!BMI160.begin(BMI160GenClass::I2C_MODE, i2c_addr)) {
    Serial.println("BMI160 initialization failed!");
    while (1); // Halt if initialization fails
  }
 
  Serial.println("BMI160 initialized successfully in I2C mode!");
}
 
void loop() {
  int gx, gy, gz; // Raw gyroscope values
  int ax, ay, az; // Raw accelerometer values
 
  // Read raw gyroscope measurements from the BMI160
  BMI160.readGyro(gx, gy, gz);
 
  // Read raw accelerometer measurements from the BMI160
  BMI160.readAccelerometer(ax, ay, az);
  absolute_accel = sqrt(sq(ax) + sq(ay) + sq(az));
  if(absolute_accel < 8250) queda_livre = true;
  if(queda_livre) if(absolute_accel > 24750) impacto = true;
  // Display the gyroscope values (X, Y, Z) on the Serial Monitor
  Serial.print("G_X:");
  Serial.print(gx);
  Serial.print(",G_Y:");
  Serial.print(gy);
  Serial.print(",G_Z:");
  Serial.print(gz);
 
  // Display the accelerometer values (X, Y, Z) on the Serial Monitor
  Serial.print(",A_X:");
  Serial.print(ax);
  Serial.print(",A_Y:");
  Serial.print(ay);
  Serial.print(",A_Z:");
  Serial.print(az);
  Serial.print(",Accel:");
  Serial.println(absolute_accel);

  if(queda_livre && imobilidade && impacto){
    digitalWrite(1,HIGH);
  }
  if(digitalRead(2)){
    queda_livre = false;
    impacto = false;
    digitalWrite(1,LOW);
  } 

  //delay(20); // Delay for readability (500ms)
}
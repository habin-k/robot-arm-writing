const int sensorPin = 2;

void setup() {
  pinMode(sensorPin, INPUT);
  Serial.begin(9600);
}

void loop() {
  int state = digitalRead(sensorPin);

  Serial.print("Sensor = ");
  Serial.println(state);

  if (state == 0) {
    Serial.println("Object detected");
  } else {
    Serial.println("No object");
  }

  delay(200);
}

FROM python:3-alpine
RUN pip install --root-user-action ignore pyserial pyyaml paho-mqtt
ADD *.py /opt/stecagrid_rs485/
WORKDIR /opt/stecagrid_rs485
ENTRYPOINT [ "python3", "/opt/stecagrid_rs485/steca_mqtt.py" ]

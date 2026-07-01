FROM python:3.11-slim

RUN useradd -m -u 1000 sandboxer && mkdir /work && chown sandboxer /work

USER sandboxer
WORKDIR /work

# No network, no pip — student code runs in isolation
CMD ["python", "-c", "print('sandbox ready')"]

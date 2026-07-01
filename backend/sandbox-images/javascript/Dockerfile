FROM node:20-alpine

RUN addgroup -g 1000 sandboxer && adduser -u 1000 -G sandboxer -s /bin/sh -D sandboxer
RUN mkdir /work && chown sandboxer:sandboxer /work

USER sandboxer
WORKDIR /work

# No network — student code runs in isolation
CMD ["node", "-e", "console.log('sandbox ready')"]

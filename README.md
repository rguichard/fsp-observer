<p align="left">
  <a href="https://flare.network/" target="blank"><img src="https://content.flare.network/Flare-2.svg" width="410" height="106" alt="Flare Logo" /></a>
</p>

# flare-observer

deploy:

```bash
docker run \
    -e RPC_URL="http://host/ext/bc/C/rpc" \
    -e IDENTITY_ADDRESS="0x0000000000000000000000000000000000000000" \
    ghcr.io/flare-foundation/fsp-observer:main
```

todos:

- more checks:
    - general/fsp:
        - [ ] check if addresses (submit, signature, sign) have enough tokens for gas
            - [ ] collect fast updates addresses and check them too
        - [ ] check for unclaimed rewards
        - [ ] check for registration:
            - [ ] aggresively report failure to register after X minutes of registration window
            - [ ] include preregistration as well
        - [ ] check if transactions are being made against correct contracts (eg.: what if relay contract switches)
        - [ ] check if transactions are being made but were sent too early or too late
    - staking:
        - [ ] check node uptime
    - ftso:
        - [ ] better ftso value analysis 
            - weird value (not just None but also 0.1 all the time, or just wildly different to median)
            - parse events to be able to tell feeds by names not by indices
        - [ ] check submit signatures signature against finalization 
    - fdc:
        - [ ] correct bitvote length (submit2 fdc)
        - [ ] check submit signatures signature against finalization 
    - fast updates:
        - [ ] recover signature from fast updates and check if updates are being made 
        - [ ] check if length of update is correct
- push notification scheme:
    - we need a general-ish extnesible framework to add more notification plugins
    - notification plugins
        - [x] stdout logging
        - [x] discord
        - [ ] slack

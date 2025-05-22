<p align="left">
  <a href="https://flare.network/" target="blank"><img src="https://content.flare.network/Flare-2.svg" width="410" height="106" alt="Flare Logo" /></a>
</p>

# flare-observer

## Deploy

Currently we support push notification over:
- discord webhook
- slack webhook
- telegram bot sendMessage method
- generic url post

All of these can be configured via env variables. All of these have `NOTIFICATION` and 
aren't a required value for the observer to start. All example values below

```bash
docker run \
    -p 8000:8000 \
    -e RPC_URL="http://host/ext/bc/C/rpc" \
    -e IDENTITY_ADDRESS="0x0000000000000000000000000000000000000000" \
    -e NOTIFICATION_DISCORD_WEBHOOK="https://discord.com/api/webhooks/secret/secret" \
    -e NOTIFICATION_TELEGRAM_BOT_TOKEN="secret" \
    -e NOTIFICATION_TELEGRAM_CHAT_ID="secret" \
    -e NOTIFICATION_SLACK_WEBHOOK="https://hooks.slack.com/services/secret/secret/secret" \
    -e NOTIFICATION_GENERIC_WEBHOOK="http://host:port/path" \
    ghcr.io/flare-foundation/fsp-observer:main
```

## Prometheus Metrics

The observer exposes Prometheus metrics on port 8000. The following metrics are available:

### General Metrics
- `observer_info`: Observer information with labels `identity_address` and `chain_id`
- `reward_epoch_info`: Current reward epoch information with label `reward_epoch_id`
- `voting_epoch_info`: Current voting epoch information with label `voting_epoch_id`

### Protocol Specific Metrics
- `ftso_submit1_total`: Total FTSO submit1 transactions (counter)
- `ftso_submit2_total`: Total FTSO submit2 transactions (counter)
- `ftso_submit_signatures_total`: Total FTSO submit signatures transactions (counter)
- `ftso_reveal_offence_total`: Total FTSO reveal offences (counter)
- `ftso_none_values_total`: Total FTSO None values submitted (counter)
- `ftso_signature_mismatch_total`: Total FTSO signature mismatches (counter)

- `fdc_submit1_total`: Total FDC submit1 transactions (counter)
- `fdc_submit2_total`: Total FDC submit2 transactions (counter)
- `fdc_submit_signatures_total`: Total FDC submit signatures transactions (counter)
- `fdc_reveal_offence_total`: Total FDC reveal offences (counter)
- `fdc_signature_mismatch_total`: Total FDC signature mismatches (counter)

### Message Level Metrics
- `message_total`: Total messages by level (counter)

### Entity Metrics
- `entity_wnat_weight`: Entity WNAT weight (gauge)
- `entity_wnat_capped_weight`: Entity WNAT capped weight (gauge)
- `entity_registration_weight`: Entity registration weight (gauge)
- `entity_normalized_weight`: Entity normalized weight (gauge)

## Todos

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
            - if you are meeting minimal conditions
            - weird value (not just None but also 0.1 all the time, or just wildly different to median)
            - parse events to be able to tell feeds by names not by indices
        - [x] check submit signatures signature against finalization 
    - fdc:
        - [ ] sample minimal conditions
        - [ ] correct bitvote length (submit2 fdc)
        - [x] check submit signatures signature against finalization 
    - fast updates:
        - [ ] recover signature from fast updates and check if updates are being made 
        - [ ] check if length of update is correct
        - [ ] sample minimal conditions
- push notification scheme:
    - we need a general-ish extnesible framework to add more notification plugins
    - notification plugins
        - [x] stdout logging
        - [x] discord
        - [x] slack
        - [x] telegram
        - [ ] pager duty
        - [x] generic post

#!/usr/bin/env bash

scv2_dir="../flare-smart-contracts-v2"

function copy_from() {
    location=$1; shift
    contracts="$@"
    for c in ${contracts[@]}; do
        file_loc="$scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json"
        if [ -f "$file_loc" ]; then
            echo "cp $scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json configuration/chain/${NETWORK}/artifacts/$c.json"
            cp "$scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json" "configuration/chain/${NETWORK}/artifacts/$c.json"
        else
            echo "NOT FOUND: $file_loc"
        fi
    done
    echo ""
}

function copy_artifacts() {
    version="$1"; shift

    echo "mkdir -p configuration/chain/${NETWORK}/artifacts/"
    echo ""
    mkdir -p "configuration/chain/${NETWORK}/artifacts/"

    echo "cp $scv2_dir/deployment/deploys/${NETWORK}.json configuration/chain/${NETWORK}/contracts.json"
    cp "$scv2_dir/deployment/deploys/${NETWORK}.json" "configuration/chain/${NETWORK}/contracts.json"
    
    echo "cp $scv2_dir/deployment/chain-config/${NETWORK}.json configuration/chain/${NETWORK}/config.json"
    cp "$scv2_dir/deployment/chain-config/${NETWORK}.json" "configuration/chain/${NETWORK}/config.json"

    protocol=(
        "FlareSystemsManager"
        "Relay"
        "VoterRegistry"
        "FlareSystemsCalculator"
        "Submission"
    )


    copy_from protocol "${protocol[@]}"
}

main () {
    export NETWORK="${1}"; shift
    copy_artifacts "$@"
}

main "$@"

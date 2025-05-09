#!/usr/bin/env bash

scv2_dir="$HOME/git/gitlab.com/flarenetwork/flare-smart-contracts-v2"

function copy_from() {
    location=$1; shift
    contracts="$@"
    for c in ${contracts[@]}; do
        file_loc="$scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json"
        if [ -f "$file_loc" ]; then
            echo "cp $scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json configuration/artifacts/$c.json"
            cp "$scv2_dir/artifacts/contracts/$location/implementation/$c.sol/$c.json" "configuration/artifacts/$c.json"
        else
            echo "NOT FOUND: $file_loc"
        fi
    done
    echo ""
}

function copy_artifacts() {
    version="$1"; shift

    echo "mkdir -p configuration/artifacts/"
    echo ""
    mkdir -p "configuration/artifacts/"

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
    copy_artifacts "$@"
}

main "$@"

#!/bin/bash

# Function variables
# 1) username for which to check ticket
USER=$1

EOS_KEYTAB=/srv/jupyterhub/private/eos.cred

if [[ ! -f "$EOS_KEYTAB" ]]; then
    exit 1;
fi

if [ "$SWAN_DEV" = "true" ]; then
    # For dev purposes, one can provide already generated token
    echo $(cat /srv/jupyterhub/private/eos.cred | base64 -w 0)
    exit 0
fi

FILENAME="/tmp/krb5cc_$USER"

KEYTAB_SPN=`klist -k $EOS_KEYTAB | grep -m 1 -Po "swaneos[12](?=@CERN.CH)"`

kS4U -v -u $USER -s $KEYTAB_SPN -proxy xrootd/eospublic.cern.ch,xrootd/eoshome.cern.ch,xrootd/eosatlas.cern.ch,xrootd/eoscms.cern.ch,xrootd/eoslhcb.cern.ch,xrootd/eosproject-i00.cern.ch,xrootd/eosproject-i01.cern.ch,xrootd/eosproject-i02.cern.ch -k $EOS_KEYTAB -c $FILENAME > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
    exit 1;
fi

echo $(cat $FILENAME | base64 -w 0)
rm $FILENAME

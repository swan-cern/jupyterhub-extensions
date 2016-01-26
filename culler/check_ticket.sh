#!/bin/bash

USER=$1
TICKET=$2
LIMIT=60000

EXP_DATE_STR=`klist $TICKET | grep 'host/eosuser-srv-m1.cern.ch@CERN.CH' | awk '{print $3," ",$4}'` 
EXP_DATE=`date --date="$EXP_DATE_STR" +%s`
NOW=`date +%s`

DIFF=$((EXP_DATE-NOW)) 
MINUTES_TO_EXP=$(($DIFF/60))

if [ "$MINUTES_TO_EXP" -lt "$LIMIT" ];
then
    echo "Renewing ticket for user $USER"
    /root/eos-fuse.sh $USER # will work when binding on the user, not the sid
else
    echo "Still $MINUTES_TO_EXP minutes to expiration for user $USER"
fi

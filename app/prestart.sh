#!/bin/sh
# Wait for couchdb and set it up.

server="couchdb"
#if [ -n $COUCHDB_URL ]
user="guest"
pass="guest"
port=5984
while [ "$1" != "" ]; do
    case $1 in
        -s | --server ) shift
                        server=$1
                        ;;
        -u | --user ) shift
                      user=$1
                      ;;
        -p | --password ) shift
                          pass=$1
                          ;;
    esac
    shift
done
#echo $server $user $pass

attempts=20
until curl -s http://$server:$port/; do
    if [[ $timeout == 0 ]]; then
        echo ERROR Failed to connect to $server:$port
        exit 1
    fi
    attempts=$((attempts-1))
    echo "CouchDB is unavailable - sleeping - $attempts attempts remaining"
    sleep 1
done

curl -s -u $user:$pass -f --head http://$server:$port/_users || curl -s -u $user:$pass -X PUT http://$server:$port/_users

curl -s -u $user:$pass -f --head http://$server:$port/_replicator || curl -s -u $user:$pass -X PUT http://$server:$port/_replicator

#curl -u $user:$pass -f --head http://$server:$port/_global_changes ||curl -u $user:$pass -X PUT http://$server:$port/_global_changes

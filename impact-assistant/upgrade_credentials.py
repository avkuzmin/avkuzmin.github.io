"""Import credentials from a running pre-Vault-all-secrets Compose installation.

Run before `compose down`. No cloud key is read, no service is stopped and no
password is rotated. Requires Python 3 and the Docker CLI on the operator host.
"""
import argparse
import json
import subprocess
import sys


def docker(*args, data=None):
    result=subprocess.run(['docker',*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:raise RuntimeError('Docker operation failed; output omitted')
    return result.stdout


def inspect(project, service):
    ids=docker('ps','-q','--filter','label=com.docker.compose.project='+project,
        '--filter','label=com.docker.compose.service='+service).decode().split()
    if len(ids)!=1:raise RuntimeError('Expected one running '+service+' container in selected project')
    return json.loads(docker('inspect',ids[0]))[0]


def env(info):
    return dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='impact-cloud-poc')
    parser.add_argument('--image',required=True,help='New application image containing import-legacy')
    args=parser.parse_args()
    pg=inspect(args.project,'postgres');neo=inspect(args.project,'neo4j');kc=inspect(args.project,'keycloak');s3=inspect(args.project,'s3')
    mounts=[m for m in s3['Mounts'] if m['Destination']=='/etc/seaweedfs' and m['Type']=='volume']
    if len(mounts)!=1:raise RuntimeError('Legacy service-config mount not found')
    config=json.loads(docker('exec',s3['Id'],'cat','/etc/seaweedfs/s3.json'))
    identities=config['identities']
    if len(identities)!=1 or len(identities[0]['credentials'])!=1:raise RuntimeError('Ambiguous S3 credentials; manual migration required')
    credentials=identities[0]['credentials'][0]
    values=dict(postgres_password=env(pg)['POSTGRES_PASSWORD'],neo4j_password=env(neo)['NEO4J_AUTH'].split('/',1)[1],
        s3_access_key=credentials['accessKey'],s3_secret_key=credentials['secretKey'],
        keycloak_admin_password=env(kc)['KC_BOOTSTRAP_ADMIN_PASSWORD'])
    docker('run','--rm','-i','--network','none','-v',mounts[0]['Name']+':/run/service-config',args.image,'import-legacy',data=json.dumps(values).encode())
    print('Credentials imported for '+args.project+'. Existing data and passwords unchanged; now upgrade Compose.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Credential import failed ('+type(error).__name__+'); details omitted. Old deployment was not stopped.',file=sys.stderr)
        raise SystemExit(1)

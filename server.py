import base64, hashlib, hmac, json, os, re, secrets, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DATA_FILE = os.environ.get('DATA_FILE', 'phonemail.json')
PORT = int(os.environ.get('PORT', '8080'))

def seed():
    now = int(time.time() * 1000)
    return {'users': {}, 'sessions': {}, 'drafts': [], 'messages': [
      {'id':'m1','from':'maya','to':['self'],'subject':'Weekend plans?','body':'Hey! Are we still on for coffee this Saturday? I found a lovely little place near the park. Let me know what time works for you ☕','time':now-1800000,'unread':True,'favorite':True,'attachments':[],'replyTo':None},
      {'id':'m2','from':'self','to':['maya'],'subject':'Weekend plans?','body':'Absolutely! How about 10:30?','time':now-1500000,'unread':False,'favorite':False,'attachments':[],'replyTo':'m1'},
      {'id':'m3','from':'alex','to':['self'],'subject':'The photos from yesterday 📸','body':'These turned out so good! I put the best ones in the album. Check them out when you get a chance.','time':now-7200000,'unread':True,'favorite':False,'attachments':[{'name':'weekend-album.zip','size':'4.2 MB'}],'replyTo':None},
      {'id':'m4','from':'self','to':['alex'],'subject':'The photos from yesterday 📸','body':'Amazing, thank you for sharing!','time':now-6900000,'unread':False,'favorite':False,'attachments':[],'replyTo':'m3'},
      {'id':'m5','from':'studio','to':['self'],'subject':'Your design files are ready','body':'Hi! Your updated brand assets are ready for review. I included the logo variations and color palette we discussed.','time':now-86400000,'unread':False,'favorite':True,'attachments':[{'name':'brand-assets.pdf','size':'2.8 MB'}],'replyTo':None},
      {'id':'m6','from':'dad','to':['self'],'subject':'Sunday dinner 🍲','body':'Your favorite is on the menu. Come by around 6?','time':now-172800000,'unread':False,'favorite':False,'attachments':[],'replyTo':None},
      {'id':'m7','from':'newsletter','to':['self'],'subject':'A little inspiration for your week','body':'Three ideas to help you slow down, reset, and make space for what matters.','time':now-259200000,'unread':False,'favorite':False,'attachments':[],'replyTo':None}
    ], 'replied': [], 'otp_flows': {}}

def load():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f: db=json.load(f)
        db.setdefault('drafts', [])
        db.setdefault('otp_flows', {})
        phones=list(db.get('users', {}).keys())
        first_phone=phones[0] if phones else None
        changed=False
        for account in db.get('users', {}).values():
            if 'phoneVerified' not in account:
                account['phoneVerified']=True
                changed=True
        for message in db.get('messages', []):
            if 'mailboxes' not in message:
                if first_phone:
                    sender=first_phone if message.get('from')=='self' else message.get('from')
                    recipients=[first_phone if p=='self' else p for p in message.get('to', [])]
                    message['from']=sender; message['to']=recipients; message['mailboxes']={}
                    for phone, account in db['users'].items():
                        addresses=[phone]+account.get('aliases', [])
                        sent=sender in addresses
                        received=any(p in addresses for p in recipients)
                        if sent or received:
                            message['mailboxes'][phone]={'folder':message.get('folder','Inbox'),'unread':bool(message.get('unread',True)) and received and not sent,'favorite':bool(message.get('favorite',False)),'important':bool(message.get('important',False))}
                else: message['mailboxes']={}
                changed=True
        for draft in db['drafts']:
            if 'owner' not in draft and first_phone:
                draft['owner']=first_phone; changed=True
        if changed: save(db)
        return db
    except (FileNotFoundError, json.JSONDecodeError): return seed()

def save(db):
    os.makedirs(os.path.dirname(DATA_FILE) or '.', exist_ok=True)
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(db, f)
    os.replace(tmp, DATA_FILE)

def public_user(user):
    return {k:v for k,v in user.items() if k not in ('salt','password')}

def e164(phone):
    raw=str(phone or '').strip()
    digits=re.sub(r'\D','',raw)
    if raw.startswith('+') and 8 <= len(digits) <= 15: return '+'+digits
    if len(digits)==10: return '+91'+digits
    if digits.startswith('91') and len(digits)==12: return '+'+digits
    if 8 <= len(digits) <= 15: return '+'+digits
    return None

def verify_request(service, endpoint, fields):
    sid=os.environ.get('TWILIO_ACCOUNT_SID'); auth=os.environ.get('TWILIO_AUTH_TOKEN')
    if not (sid and auth and service): raise RuntimeError('Twilio Verify is not configured. Set the Twilio account SID, auth token, and Verify Service SID.')
    url=f'https://verify.twilio.com/v2/Services/{service}/{endpoint}'
    req=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode(),headers={'Authorization':'Basic '+base64.b64encode(f'{sid}:{auth}'.encode()).decode(),'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=15) as response: return json.loads(response.read())

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, code, obj, typ='application/json; charset=utf-8'):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type', typ); self.send_header('Content-Length', str(len(data))); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type,Authorization'); self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS'); self.end_headers(); self.wfile.write(data)
    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
        except Exception: return {}
    def sms_notice(self, phone, sender, subject):
        sid=os.environ.get('TWILIO_ACCOUNT_SID'); auth=os.environ.get('TWILIO_AUTH_TOKEN'); source=os.environ.get('TWILIO_FROM_NUMBER')
        if not (sid and auth and source): return
        target=('+'+phone) if len(phone)>10 else '+91'+phone
        form=urllib.parse.urlencode({'To':target,'From':source,'Body':f'You have received an email from {sender}. Subject: {subject}.'}).encode()
        request=urllib.request.Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',data=form,headers={'Authorization':'Basic '+base64.b64encode(f'{sid}:{auth}'.encode()).decode(),'Content-Type':'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(request,timeout=8) as response: response.read()
        except Exception as exc: print('Twilio SMS delivery failed:',exc,flush=True)
    def user(self, db):
        token=self.headers.get('Authorization','').replace('Bearer ','')
        phone=db['sessions'].get(token)
        return (token,db['users'].get(phone)) if phone else (token,None)
    def do_OPTIONS(self): self.send(204,{})
    def do_GET(self):
        path=urlparse(self.path).path
        if path.startswith('/api/'):
            db=load(); token,user=self.user(db)
            if path=='/api/me':
                return self.send(200, {'authenticated':bool(user),'user':public_user(user)} if user else {'authenticated':False})
            if not user: return self.send(401,{'error':'Please sign in to continue.'})
            if path=='/api/messages':
                messages=[]
                for message in db['messages']:
                    mailbox=message.get('mailboxes',{}).get(user['phone'])
                    if mailbox: messages.append({k:v for k,v in message.items() if k!='mailboxes'}|mailbox)
                drafts=[draft for draft in db['drafts'] if draft.get('owner')==user['phone']]
                return self.send(200,{'messages':messages,'drafts':drafts,'user':public_user(user)})
            return self.send(404,{'error':'Not found'})
        asset='index.html' if path=='/' else path.lstrip('/')
        if '..' in asset: return self.send(403,b'Forbidden','text/plain')
        try:
            with open(asset,'rb') as f: data=f.read()
            typ='text/html; charset=utf-8' if asset.endswith('.html') else 'text/css; charset=utf-8' if asset.endswith('.css') else 'application/javascript; charset=utf-8' if asset.endswith('.js') else 'image/svg+xml' if asset.endswith('.svg') else 'application/octet-stream'
            self.send(200,data,typ)
        except FileNotFoundError: self.send(404,b'Not found','text/plain')
    def do_POST(self):
        path=urlparse(self.path).path; data=self.body(); db=load(); token,user=self.user(db)
        if path=='/api/inbound':
            secret=os.environ.get('INBOUND_WEBHOOK_TOKEN','')
            if not secret or not hmac.compare_digest(self.headers.get('X-Webhook-Token',''),secret): return self.send(401,{'error':'Invalid webhook token.'})
            recipient=re.sub(r'\D','',data.get('to','')); u=db['users'].get(recipient)
            if not u: return self.send(404,{'error':'No PhoneMail account found for this recipient.'})
            msg={'id':secrets.token_urlsafe(18),'from':data.get('from','Unknown sender'),'to':[recipient],'subject':data.get('subject','(no subject)'),'body':data.get('body',''),'time':int(time.time()*1000),'mailboxes':{recipient:{'folder':'Inbox','unread':True,'favorite':False,'important':False}},'attachments':[],'replyTo':None}
            db['messages'].append(msg); save(db)
            if not u.get('hasApp',False): self.sms_notice(recipient,msg['from'],msg['subject'])
            return self.send(201,{'message':msg})
        if path=='/api/register':
            phone=re.sub(r'\D','',data.get('phone',''))
            if len(phone)<7 or len(phone)>15: return self.send(400,{'error':'Enter a valid phone number.'})
            password=data.get('password','')
            if len(password)<4: return self.send(400,{'error':'Password must be at least 4 characters.'})
            if phone in db['users']: return self.send(409,{'error':'This number already has a PhoneMail account. Sign in instead.'})
            salt=secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()
            db['users'][phone]={'phone':phone,'email':phone+'@phonemail.com','name':data.get('name','').strip() or 'TridentChat friend','salt':salt,'password':digest,'phoneVerified':False,'hasApp':bool(data.get('hasApp',True)),'language':data.get('language','English'),'aliases':[],'avatar':None,'darkMode':False,'magnification':100}
            save(db); return self.send(201,{'requiresVerification':True,'user':public_user(db['users'][phone])})
        if path=='/api/login':
            phone=re.sub(r'\D','',data.get('phone','')); u=db['users'].get(phone)
            if not u or not hmac.compare_digest(u['password'],hashlib.pbkdf2_hmac('sha256',data.get('password','').encode(),u['salt'].encode(),180000).hex()): return self.send(401,{'error':'Phone number or password is incorrect.'})
            if not u.get('phoneVerified',True): return self.send(403,{'error':'Verify this phone number to finish creating your account.','verificationRequired':True})
            token=secrets.token_urlsafe(32); db['sessions'][token]=phone; save(db); return self.send(200,{'token':token,'user':public_user(u)})
        if path=='/api/otp/start':
            phone=re.sub(r'\D','',data.get('phone','')); target=e164(data.get('phone')); mode=data.get('mode','login'); channel=data.get('channel','sms')
            if not target or len(phone)<7 or len(phone)>15: return self.send(400,{'error':'Enter a valid phone number. Use +country code for numbers outside India.'})
            if mode not in ('login','verify') or channel not in ('sms','call'): return self.send(400,{'error':'Choose SMS or phone call verification.'})
            exists=phone in db['users']
            if mode=='login' and not exists: return self.send(404,{'error':'No account found for this number. Switch to create an account.'})
            if mode=='verify' and not exists: return self.send(404,{'error':'Create your account with a password first, then verify this phone.'})
            if mode=='verify' and db['users'][phone].get('phoneVerified',True): return self.send(409,{'error':'This phone number is already verified. Sign in with your password.'})
            if mode=='login' and not db['users'][phone].get('phoneVerified',True): return self.send(403,{'error':'Finish phone verification before signing in.','verificationRequired':True})
            try: verification=verify_request(os.environ.get('TWILIO_VERIFY_SERVICE_SID'),'Verifications',{'To':target,'Channel':channel})
            except Exception: return self.send(502,{'error':'Could not send the code. Check the Twilio Verify Service settings and make sure this number is verified in your trial account.'})
            flow=secrets.token_urlsafe(24); db['otp_flows'][flow]={'phone':phone,'to':target,'mode':mode,'created':int(time.time())}; save(db)
            return self.send(200,{'flowId':flow,'channel':channel,'status':verification.get('status','pending')})
        if path=='/api/otp/check':
            flow=str(data.get('flowId','')); pending=db.get('otp_flows',{}).get(flow); code=str(data.get('code','')).strip()
            if not pending or int(time.time())-pending.get('created',0)>600: return self.send(400,{'error':'That code request expired. Request a new code.'})
            try: result=verify_request(os.environ.get('TWILIO_VERIFY_SERVICE_SID'),'VerificationCheck',{'To':pending['to'],'Code':code})
            except Exception: return self.send(400,{'error':'That code is incorrect or expired. Try again or request a new one.'})
            if result.get('status')!='approved': return self.send(400,{'error':'That code is incorrect or expired. Try again.'})
            phone=pending['phone']; u=db['users'].get(phone)
            if not u: return self.send(404,{'error':'No account found for this number.'})
            if pending['mode']=='verify': u['phoneVerified']=True
            elif not u.get('phoneVerified',True): return self.send(403,{'error':'Finish phone verification before signing in.'})
            db['otp_flows'].pop(flow,None); token=secrets.token_urlsafe(32); db['sessions'][token]=phone; save(db); return self.send(200,{'token':token,'user':public_user(u)})
        if not user: return self.send(401,{'error':'Please sign in to continue.'})
        if path=='/api/logout': db['sessions'].pop(token,None); save(db); return self.send(200,{'ok':True})
        if path=='/api/messages':
            recipients=[re.sub(r'\D','',p) for p in data.get('to',[]) if re.sub(r'\D','',p)]
            if not recipients: return self.send(400,{'error':'Add at least one recipient phone number.'})
            mid=secrets.token_urlsafe(18); mailboxes={user['phone']:{'folder':'Inbox','unread':False,'favorite':False,'important':False}}
            for phone, account in db['users'].items():
                addresses=[phone]+account.get('aliases', [])
                if any(recipient in addresses for recipient in recipients):
                    mailboxes.setdefault(phone,{'folder':'Inbox','unread':True,'favorite':False,'important':False})
            msg={'id':mid,'from':user['phone'],'to':recipients,'subject':data.get('subject','').strip() or '(no subject)','body':data.get('body','').strip(),'time':int(time.time()*1000),'mailboxes':mailboxes,'attachments':[],'replyTo':data.get('replyTo')}
            db['messages'].append(msg)
            if data.get('draftId'): db['drafts']=[draft for draft in db['drafts'] if not (draft['id']==data['draftId'] and draft.get('owner')==user['phone'])]
            if msg['replyTo']: db['replied'].append(msg['replyTo'])
            for recipient in recipients:
                target=db['users'].get(recipient)
                if target and not target.get('hasApp',False): self.sms_notice(recipient,user['email'],msg['subject'])
            save(db); return self.send(201,{'message':msg})
        if path=='/api/drafts':
            draft_id=data.get('id') or secrets.token_hex(8)
            draft={'id':draft_id,'owner':user['phone'],'to':[re.sub(r'\D','',p) for p in data.get('to',[]) if re.sub(r'\D','',p)],'subject':data.get('subject','').strip(),'body':data.get('body','').strip(),'time':int(time.time()*1000),'folder':'Drafts'}
            db['drafts']=[item for item in db['drafts'] if not (item['id']==draft_id and item.get('owner')==user['phone'])]
            db['drafts'].append(draft); save(db); return self.send(200,{'draft':draft})
        if path=='/api/profile':
            for k in ('name','language','avatar','darkMode','magnification'):
                if k in data: user[k]=data[k]
            save(db); return self.send(200,{'user':public_user(user)})
        if path=='/api/aliases':
            alias=re.sub(r'\D','',data.get('phone',''))
            if len(alias)<7 or len(alias)>15: return self.send(400,{'error':'Enter a valid phone number.'})
            if alias not in user['aliases']: user['aliases'].append(alias)
            save(db); return self.send(200,{'user':public_user(user)})
        if path=='/api/mark':
            m=next((m for m in db['messages'] if m['id']==data.get('id') and user['phone'] in m.get('mailboxes',{})),None)
            field=data.get('field','unread'); value=data.get('value',False)
            if field not in ('unread','favorite','important','folder'): return self.send(400,{'error':'Unsupported message action.'})
            if field=='folder' and value not in ('Inbox','Spam','Trash'): return self.send(400,{'error':'Invalid mail folder.'})
            if m: m['mailboxes'][user['phone']][field]=value; save(db)
            return self.send(200,{'ok':True})
        return self.send(404,{'error':'Not found'})

if __name__=='__main__': ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()

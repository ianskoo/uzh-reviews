import os 
from pymongo import MongoClient
from pprint import pprint
from numpy import mean
from textwrap import dedent
from datetime import datetime
import requests

"""
------------Useful Mongo commands:

Create MongoDB docker container named pybestande with persistent data:
sudo docker run -d -p 27017:27017 --name pybestande --restart unless-stopped -v mongo-data:/data/db mongo:latest

Start mongodb with:
sudo docker start pybestande;

Get into mongo shell with:
sudo docker exec -it pybestande mongosh;

Import JSON to mongodb:
sudo docker exec -i pybestande bash -c 'mongoimport -c pybestande --jsonArray' < /home/chris/scripts/python-bestande/data/bestande_reviews.json;

Create index for text search:
db.pybestande.createIndex({courseNameShort:"text"})

"""


class TelegramBot():
    
    def __init__(self) -> None:
        
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        
        with open(os.path.join(self.dir_path, 'data/token.txt'), 'r') as f:
            lines = f.readlines()
            
        self.base_chat_id = lines[0]
        self.token = lines[1]

    def send(self, chat_id:int, msg:str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage?chat_id={chat_id}&text={msg}&parse_mode=markdown"
        res = requests.get(url).json()
        # print(res)
    
    def receive(self, id_offset:int, polling_timeout:int=20):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={id_offset}&timeout={polling_timeout}"
        return requests.get(url).json()
    


if __name__ == "__main__":
    # Init Mongo
    client = MongoClient("mongodb://localhost:27017/")
    db = client.test # Connect to db
    data = db.pybestande
    
    # init telegram bot
    tgBot = TelegramBot()
    
    id_offset = 0
    debug = False

    try:
        while True:
            # Get request
            try:
                req = tgBot.receive(id_offset=id_offset, polling_timeout=30)
                if debug:
                    print("Offset: ", id_offset)
                    pprint(req)
                if req['result']:
                    id_offset = req['result'][0]['update_id'] + 1
                    chat_id = req['result'][0]['message']['chat']['id']
                    
                    query_lst = req['result'][0]['message']['text'].split(',')
                    query_sname = query_lst[0]
                    query_uni = ""
                    if len(query_lst) == 2:
                        query_uni = query_lst[1].upper().strip()
                    
                    # Log request
                    with open(os.path.join(tgBot.dir_path, 'log.txt'), 'a') as f:
                        f.write("".join([f"{datetime.now()}: ",
                                         f"{req['result'][0]['message']['from']['first_name']} ",
                                         f"wrote {req['result'][0]['message']['text']}\n"]))
                else:
                    continue
            except Exception as e:
                tgBot.send(chat_id, f"*Command not understood. Please try again.*\nRequest format: <course shortname>, <UZH/ETH>")
                print("Exception: ", e)
                id_offset = req['result'][0]['update_id'] + 1
                continue
            
            # Look up if shortname matches perfectly to a db entry
            search = {'courseNameShort':query_sname}
            if query_uni:
                search['university'] = query_uni
                
            if not list(data.find(search, {'courseNameShort': 1, '_id':0}).limit(100)):
                # Text search query and use most probable course
                candidates = [cname['courseNameShort'] for cname in data.find({"$text": {"$search": query_sname}}, 
                                                                              {'courseNameShort': 1, '_id':0}).limit(500)]         
                search['courseNameShort'] = max(set(candidates), key = candidates.count)
            
            # Look for reviews
            revs = list(data.find(search, 
                                  {'review':1, 
                                   'score':1, 
                                   'upvotes':1, 
                                   'downvotes':1, 
                                   'university':1,
                                   '_id':0}))
            
            # Check if course is unique between UZH/ETH if no uni specified
            unis = set(rev['university'] for rev in revs)
            if len(unis) > 1:
                tgBot.send(chat_id, 
                           "*Warning! The course shortname is not unique between UZH/ETH*, " +
                            "please specify which university you want after the course name as follows:\n\n" +
                            "Request format: <course shortname>, <UZH/ETH>")
                continue
            
            # Write messages for written reviews
            msgs = []
            if revs:
                for rev in revs:
                    # pprint(rev)
                    if not rev['review']:
                        continue
                        
                    msg = f"{rev['score'] * '★'}{(5-rev['score']) * '☆'}"
                    
                    if 'upvotes' in rev and 'downvotes' in rev:
                        msg += f"\t\t\t{rev['upvotes']} 👍  {rev['downvotes']} 👎"
                        
                    
                    msg += f"\n\n{rev['review']}"
                    msgs.append(msg)
            
                # Compute average score
                scores = [rev['score'] for rev in revs]
                avg_score = mean(scores)
            
            # Send reply
            if msgs:
                tgBot.send(chat_id, dedent(
                    f"""
                    *{search['courseNameShort']}*  {query_uni}
                    Average review score: {round(avg_score, 1)}\t{round(avg_score) * '★'}{(5-round(avg_score)) * '☆'}
                    Reviews count: {len(scores)}
                    
                    Distribution:
                    ★★★★★ {round(scores.count(5)/len(scores)*100)}%
                    ★★★★☆ {round(scores.count(4)/len(scores)*100)}%
                    ★★★☆☆ {round(scores.count(3)/len(scores)*100)}%
                    ★★☆☆☆ {round(scores.count(2)/len(scores)*100)}%
                    ★☆☆☆☆ {round(scores.count(1)/len(scores)*100)}%
                    
                    Written reviews:
                    """
                    )
                )
                
                for msg in msgs:
                    tgBot.send(chat_id, msg)
            else:
                tgBot.send(chat_id, f"*No reviews found.* Check the course name (case sensitive, for now) or deal with it 🤡")
        
    except Exception as e:
        tgBot.send(tgBot.base_chat_id, f"I encountered an error. Shutting down. Error: {e}")
        exit()
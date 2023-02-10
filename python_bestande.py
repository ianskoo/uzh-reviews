from pymongo import MongoClient
from pprint import pprint
import requests

"""
------------Useful Mongo commands:

Create MongoDB docker container named pybestande with persistent data:
sudo docker run -d -p 27017:27017 --name pybestande -v mongo-data:/data/db mongo:latest

Start mongodb with:
sudo docker start pybestande;

Get into mongo shell with:
sudo docker exec -it pybestande mongosh;

Import JSON to mongodb:
sudo docker exec -i pybestande bash -c 'mongoimport -c pybestande --jsonArray' < /home/chris/scripts/python-bestande/data/bestande_reviews.json;

"""


class TelegramBot():
    
    def __init__(self) -> None:
        
        with open('data/token.txt', 'r') as f:
            lines = f.readlines()
            
        self.chat_id = lines[0]
        self.token = lines[1]

    def send(self, msg:str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage?chat_id={self.chat_id}&text={msg}&parse_mode=markdown"
        res = requests.get(url).json()
        # print(res)
    
    def receive(self, id_offset:int, polling_timeout:int=20):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates?chat_id={self.chat_id}&offset={id_offset}&timeout={polling_timeout}"
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
                    course_shortname = req['result'][0]['message']['text']
                    id_offset = req['result'][0]['update_id'] + 1
                else:
                    continue
            except Exception as e:
                # tgBot.send(f"*Command not understood. Please try again.*\nRequest format: <course shortname>")
                if debug:
                    print("Exception: ", e)
                id_offset = req['result'][0]['update_id'] + 1
                continue
            
            # Look for reviews
            msgs = []
            revs = list(data.find({'courseNameShort':course_shortname}, {'review':1, 'score':1, 'upvotes':1, 'downvotes':1}))
            
            if revs:
                for rev in revs:
                    # pprint(rev)
                    if not rev['review']:
                        rev['review'] = ''
                        
                    msg = f"{rev['score'] * '★'}{(5-rev['score']) * '☆'}"
                    
                    if 'upvotes' in rev and 'downvotes' in rev:
                        msg += f"\t\t\t{rev['upvotes']} 👍  {rev['downvotes']} 👎"
                    
                    msg += f"\n\n{rev['review']}"
                    msgs.append(msg)
            
            # Send reply
            if msgs:
                tgBot.send(f"*Here's the reviews for {course_shortname}:*")
                
                for msg in msgs:
                    tgBot.send(msg)
            else:
                tgBot.send(f"*No reviews found. Check the course name or deal with it.*")
        
    except Exception as e:
        tgBot.send(f"I encountered an error. Shutting down. Error: {e}")
        exit()
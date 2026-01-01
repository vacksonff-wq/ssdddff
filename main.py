from pyrubi import Client
from pyrubi.types import Message

client = Client("mySelf")

@client.on_message(regexp="hello")
def send_hello(message: Message):
    message.reply("**hello** __from__ ##pyrubi##")

client.run()

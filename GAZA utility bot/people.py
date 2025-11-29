import discord

from discord.ext import commands

class CustomResponses(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

    @commands.Cog.listener()

    async def on_message(self, message):

        # Ignore messages from the bot itself

        if message.author == self.bot.user:

            return

        

        message_content = message.content.lower()

        

        # Response for "sensei"

        if "sensei" in message_content:

            await message.channel.send("sensei tuff guy but ghosts to much")

        

        # Response for "KINGBOSSALI22"

        elif "kingbossali22" in message_content:

            await message.channel.send("Has to much aura. Vote him for Co owner")

        

        # Response for "neko"

        elif "neko" in message_content:

            await message.channel.send("lal kabutar")

        

        # Response for "friendly"

        elif "friendly" in message_content:

            await message.channel.send("@friendly.osi is very friendly")

        

        # Response for "eiscrazyyy"

        elif "eiscrazyyy" in message_content:

            await message.channel.send("Baji Churail")

        

        # Response for "Ibn Al Mansur"

        elif "ibn al mansur" in message_content:

            await message.channel.send(f"Ibn Al Mansur is Mujahid <:Hmm:1370328554012803094>")

        

        # Response for "honey"

        elif "honey" in message_content:

            await message.channel.send("i love my mom and dad and my sisters and my friends 💕")

async def setup(bot):

    await bot.add_cog(CustomResponses(bot))
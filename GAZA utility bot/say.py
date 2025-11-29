import discord

from discord.ext import commands

class SayCommand(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.allowed_users = [1154644028718075944, 1274667778300706866, 951863963132506232]

    @commands.command(name='say')

    async def say(self, ctx, *, message: str):

        """Repeats what the user says and deletes their command"""

        # Check if user is allowed to use this command

        if ctx.author.id not in self.allowed_users:

            return  # Do absolutely nothing - no deletion, no response

        

        # Delete the user's command message

        await ctx.message.delete()

        # Send the bot's response

        await ctx.send(message)

async def setup(bot):

    await bot.add_cog(SayCommand(bot))
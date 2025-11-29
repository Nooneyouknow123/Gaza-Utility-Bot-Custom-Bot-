import discord
from discord.ext import commands
from discord import app_commands

class SayCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_users = [1154644028718075944, 1274667778300706866, 951863963132506232]

    @app_commands.command(name="say", description="Make the bot say something in a specific channel")
    @app_commands.describe(
        channel="The channel where the message should be sent",
        message="The message you want the bot to say"
    )
    async def say(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        """Make the bot say something in a specific channel"""
        # Check if user is allowed
        if interaction.user.id not in self.allowed_users:
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        # Send the message in the specified channel
        await channel.send(message)
        # Confirm to the user
        await interaction.response.send_message(f"Message sent in {channel.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SayCommand(bot))
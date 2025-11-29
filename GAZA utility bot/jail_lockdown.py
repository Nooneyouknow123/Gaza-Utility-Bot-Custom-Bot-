# jail_lockdown_cog.py

import discord

from discord.ext import commands

import sqlite3

import logging

import asyncio

from typing import Optional

logger = logging.getLogger("jail_lockdown_cog")

class JailLockdownCog(commands.Cog):

    def __init__(self, bot: commands.Bot):

        self.bot = bot

        self._db_lock = asyncio.Lock()

        self._processing_guilds = set()  # Track guilds being processed

        self._init_db()

    def _init_db(self):

        """Initialize database tables"""

        try:

            conn = sqlite3.connect("jail_system.db")

            c = conn.cursor()

            c.execute('''

                CREATE TABLE IF NOT EXISTS guild_config (

                    guild_id INTEGER PRIMARY KEY,

                    jail_role INTEGER,

                    appeals_channel INTEGER

                )

            ''')

            conn.commit()

            conn.close()

            logger.info("Database initialized")

        except Exception as e:

            logger.error(f"Failed to initialize database: {e}")

    async def _run_db(self, fn, *args, **kwargs):

        """Run DB operations in executor"""

        async with self._db_lock:

            loop = asyncio.get_running_loop()

            return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def _get_guild_config_sync(self, guild_id: int):

        """Sync function to get guild config from DB"""

        try:

            conn = sqlite3.connect("jail_system.db")

            conn.row_factory = sqlite3.Row

            c = conn.cursor()

            r = c.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)).fetchone()

            conn.close()

            return dict(r) if r else None

        except Exception as e:

            logger.error(f"DB error in _get_guild_config_sync: {e}")

            return None

    async def _rate_limit_delay(self, guild_id: int):

        """Add delay to respect rate limits"""

        if guild_id in self._processing_guilds:

            # Longer delay if this guild is already being processed

            await asyncio.sleep(2.0)

        else:

            # Standard delay

            await asyncio.sleep(0.5)

    async def _clear_existing_overrides(self, channel, jail_role):

        """Clear existing permission overrides for jail role"""

        try:

            # Check if there's an existing override

            if channel.overwrites and jail_role in channel.overwrites:

                await channel.set_permissions(jail_role, overwrite=None)

                logger.info(f"Cleared existing overrides for {channel.name}")

                await self._rate_limit_delay(channel.guild.id)

        except discord.HTTPException as e:

            if e.status == 429:  # Rate limited

                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5

                logger.warning(f"Rate limited while clearing overrides, retrying in {retry_after}s")

                await asyncio.sleep(retry_after)

                await self._clear_existing_overrides(channel, jail_role)  # Retry

            else:

                logger.warning(f"Could not clear overrides for {channel.name}: {e}")

        except Exception as e:

            logger.warning(f"Could not clear overrides for {channel.name}: {e}")

    async def _setup_channel_permissions(self, channel, jail_role, appeals_channel_id=None):

        """Set up permissions for a single channel for jailed users"""

        try:

            # Clear any existing overrides first

            await self._clear_existing_overrides(channel, jail_role)

            

            # If this is the appeals channel, allow read but not send

            if channel.id == appeals_channel_id:

                await channel.set_permissions(

                    jail_role,

                    read_messages=True,

                    send_messages=False,

                    read_message_history=True,

                    add_reactions=False

                )

                logger.info(f"Set appeals permissions for {channel.name}")

            # Handle text channels

            elif isinstance(channel, discord.TextChannel):

                await channel.set_permissions(

                    jail_role,

                    read_messages=False,

                    send_messages=False,

                    view_channel=False

                )

                logger.info(f"Set text channel permissions for {channel.name}")

            # Handle voice channels

            elif isinstance(channel, discord.VoiceChannel):

                await channel.set_permissions(

                    jail_role,

                    connect=False,

                    view_channel=False,

                    speak=False

                )

                logger.info(f"Set voice channel permissions for {channel.name}")

            # Handle categories

            elif isinstance(channel, discord.CategoryChannel):

                await channel.set_permissions(

                    jail_role,

                    read_messages=False,

                    send_messages=False,

                    connect=False,

                    view_channel=False

                )

                logger.info(f"Set category permissions for {channel.name}")

            # Handle forum channels

            elif hasattr(discord, 'ForumChannel') and isinstance(channel, discord.ForumChannel):

                await channel.set_permissions(

                    jail_role,

                    read_messages=False,

                    send_messages=False,

                    view_channel=False

                )

                logger.info(f"Set forum channel permissions for {channel.name}")

            # Handle stage channels

            elif isinstance(channel, discord.StageChannel):

                await channel.set_permissions(

                    jail_role,

                    connect=False,

                    view_channel=False

                )

                logger.info(f"Set stage channel permissions for {channel.name}")

            await self._rate_limit_delay(channel.guild.id)

            return True

        except discord.HTTPException as e:

            if e.status == 429:  # Rate limited

                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5

                logger.warning(f"Rate limited in _setup_channel_permissions, retrying in {retry_after}s")

                await asyncio.sleep(retry_after)

                return await self._setup_channel_permissions(channel, jail_role, appeals_channel_id)  # Retry

            else:

                logger.error(f"HTTP error setting permissions for {channel.name}: {e}")

                return False

        except discord.Forbidden:

            logger.error(f"Bot lacks permissions to modify {channel.name}")

            return False

        except Exception as e:

            logger.error(f"Unexpected error setting permissions for {channel.name}: {e}")

            return False

    @commands.Cog.listener()

    async def on_guild_channel_create(self, channel):

        """Automatically set jail permissions when a new channel is created"""

        try:

            guild = channel.guild

            

            # Get guild config

            cfg = await self._run_db(self._get_guild_config_sync, guild.id)

            if not cfg or not cfg.get("jail_role"):

                return

            

            jail_role = guild.get_role(cfg["jail_role"])

            if not jail_role:

                return

            

            appeals_channel_id = cfg.get("appeals_channel")

            

            # Wait a moment for channel to be fully created

            await asyncio.sleep(2)

            

            # Set permissions for the new channel

            success = await self._setup_channel_permissions(channel, jail_role, appeals_channel_id)

            

            if success:

                logger.info(f"Automatically set jail permissions for new channel: {channel.name}")

                

        except Exception as e:

            logger.error(f"Failed to auto-set permissions for new channel {channel.name}: {e}")

    async def _process_channels_batch(self, channels, jail_role, appeals_channel_id, progress_callback=None):

        """Process channels in batches with proper rate limiting"""

        processed = 0

        failed = 0

        

        for i, channel in enumerate(channels):

            try:

                success = await self._setup_channel_permissions(channel, jail_role, appeals_channel_id)

                if success:

                    processed += 1

                else:

                    failed += 1

                    

                # Update progress every 5 channels (reduced frequency)

                if progress_callback and (i + 1) % 5 == 0:

                    await progress_callback(i + 1, len(channels), processed, failed)

                    

            except Exception as e:

                failed += 1

                logger.error(f"Failed to set permissions for {channel.name}: {e}")

        

        return processed, failed

    @commands.command(name="lockdownjail")

    @commands.has_permissions(administrator=True)

    async def lockdown_jail(self, ctx: commands.Context):

        """Automatically set up channel permissions so jailed users can't see any channels except appeals"""

        if ctx.guild.id in self._processing_guilds:

            return await ctx.send(embed=discord.Embed(

                title="⏳ Already Processing",

                description="This guild is already being processed. Please wait for the current operation to complete.",

                color=discord.Color.orange()

            ))

        

        try:

            self._processing_guilds.add(ctx.guild.id)

            

            guild = ctx.guild

            cfg = await self._run_db(self._get_guild_config_sync, guild.id)

            

            if not cfg or not cfg.get("jail_role"):

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Jail system not set up. Use `.setupjail` first.",

                    color=discord.Color.red()

                ))

            

            jail_role = guild.get_role(cfg["jail_role"])

            if not jail_role:

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Jail role not found.",

                    color=discord.Color.red()

                ))

            

            appeals_channel = guild.get_channel(cfg["appeals_channel"])

            if not appeals_channel:

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Appeals channel not found.",

                    color=discord.Color.red()

                ))

            

            # Verify bot has necessary permissions

            bot_member = guild.get_member(self.bot.user.id)

            if not bot_member.guild_permissions.manage_roles:

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Bot needs 'Manage Roles' permission.",

                    color=discord.Color.red()

                ))

            embed = discord.Embed(

                title="🔒 Jail Lockdown Setup",

                description="Setting up channel permissions... This may take a while for large servers.",

                color=discord.Color.orange()

            )

            embed.add_field(name="📝 Note", 

                          value="Processing channels with rate limit protection. This prevents API bans.", 

                          inline=False)

            embed.add_field(name="⏰ Estimated Time", 

                          value=f"Approx {len(guild.channels) * 0.7:.0f} seconds for {len(guild.channels)} channels", 

                          inline=False)

            msg = await ctx.send(embed=embed)

            async def update_progress(current, total, processed, failed):

                """Update progress embed"""

                progress_embed = discord.Embed(

                    title="🔒 Jail Lockdown Setup",

                    description=f"Progress: {current}/{total} channels processed...",

                    color=discord.Color.orange()

                )

                progress_embed.add_field(name="✅ Processed", value=processed, inline=True)

                progress_embed.add_field(name="❌ Failed", value=failed, inline=True)

                progress_embed.add_field(name="⏱️ Status", value="Respecting rate limits...", inline=True)

                await msg.edit(embed=progress_embed)

            # Process all channels

            processed, failed = await self._process_channels_batch(

                guild.channels, 

                jail_role, 

                appeals_channel.id,

                progress_callback=update_progress

            )

            # Final completion embed

            complete_embed = discord.Embed(

                title="✅ Jail Lockdown Complete",

                description=f"Jailed users will now only see the appeals channel.",

                color=discord.Color.green()

            )

            complete_embed.add_field(

                name="📊 Results",

                value=f"✅ Processed: {processed} channels\n❌ Failed: {failed}",

                inline=False

            )

            complete_embed.add_field(

                name="🔓 Appeals Channel",

                value=f"{appeals_channel.mention} - Jailed users can see but not send messages",

                inline=False

            )

            complete_embed.add_field(

                name="🤖 Auto-Setup",

                value="New channels will automatically get jail permissions configured!",

                inline=False

            )

            

            await msg.edit(embed=complete_embed)

            

        except Exception as e:

            logger.exception("lockdown_jail failed")

            await ctx.send(embed=discord.Embed(

                title="❌ Error",

                description=f"Lockdown failed: {e}",

                color=discord.Color.red()

            ))

        finally:

            self._processing_guilds.discard(ctx.guild.id)

    @commands.command(name="fixjailperms")

    @commands.has_permissions(administrator=True)

    async def fix_jail_perms(self, ctx: commands.Context):

        """Fix jail permissions for all existing channels"""

        if ctx.guild.id in self._processing_guilds:

            return await ctx.send(embed=discord.Embed(

                title="⏳ Already Processing",

                description="This guild is already being processed. Please wait for the current operation to complete.",

                color=discord.Color.orange()

            ))

        

        try:

            self._processing_guilds.add(ctx.guild.id)

            

            guild = ctx.guild

            cfg = await self._run_db(self._get_guild_config_sync, guild.id)

            

            if not cfg or not cfg.get("jail_role"):

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Jail system not set up. Use `.setupjail` first.",

                    color=discord.Color.red()

                ))

            

            jail_role = guild.get_role(cfg["jail_role"])

            if not jail_role:

                return await ctx.send(embed=discord.Embed(

                    title="❌ Error",

                    description="Jail role not found.",

                    color=discord.Color.red()

                ))

            

            appeals_channel_id = cfg.get("appeals_channel")

            

            embed = discord.Embed(

                title="🔧 Fixing Jail Permissions",

                description="Checking and fixing permissions for all channels with rate limit protection...",

                color=discord.Color.orange()

            )

            embed.add_field(name="⏰ Note", 

                          value="This will take time to avoid rate limits. Please be patient.", 

                          inline=False)

            msg = await ctx.send(embed=embed)

            

            processed = 0

            fixed = 0

            failed = 0

            

            for i, channel in enumerate(guild.channels):

                try:

                    processed += 1

                    

                    # Check if permissions are already correct

                    perms = channel.permissions_for(jail_role)

                    

                    needs_fix = False

                    

                    if channel.id == appeals_channel_id:

                        # Should have read but not send

                        if not perms.read_messages or perms.send_messages:

                            needs_fix = True

                    else:

                        # Should not have access

                        if perms.read_messages or perms.view_channel:

                            needs_fix = True

                    

                    if needs_fix:

                        success = await self._setup_channel_permissions(channel, jail_role, appeals_channel_id)

                        if success:

                            fixed += 1

                    

                    # Update progress every 10 channels

                    if (i + 1) % 10 == 0:

                        progress_embed = discord.Embed(

                            title="🔧 Fixing Jail Permissions",

                            description=f"Progress: {i+1}/{len(guild.channels)} channels checked...",

                            color=discord.Color.orange()

                        )

                        progress_embed.add_field(name="✅ Checked", value=processed, inline=True)

                        progress_embed.add_field(name="🔧 Fixed", value=fixed, inline=True)

                        progress_embed.add_field(name="❌ Failed", value=failed, inline=True)

                        await msg.edit(embed=progress_embed)

                            

                except Exception as e:

                    failed += 1

                    logger.error(f"Failed to fix permissions for {channel.name}: {e}")

            

            complete_embed = discord.Embed(

                title="✅ Permissions Fixed",

                color=discord.Color.green()

            )

            complete_embed.add_field(name="Channels Processed", value=processed, inline=True)

            complete_embed.add_field(name="Permissions Fixed", value=fixed, inline=True)

            complete_embed.add_field(name="Failures", value=failed, inline=True)

            

            await msg.edit(embed=complete_embed)

            

        except Exception as e:

            logger.exception("fixjailperms failed")

            await ctx.send(embed=discord.Embed(

                title="❌ Error",

                description=f"Fix permissions failed: {e}",

                color=discord.Color.red()

            ))

        finally:

            self._processing_guilds.discard(ctx.guild.id)

async def setup(bot: commands.Bot):

    await bot.add_cog(JailLockdownCog(bot))
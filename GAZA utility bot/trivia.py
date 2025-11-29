import discord
from discord.ext import commands
import asyncio
import random
from typing import List, Dict
from trivia_db import TriviaDatabase

class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}
        self.db = TriviaDatabase()

    class TriviaGame:
        def __init__(self, category: str, questions: List[Dict], starter: discord.Member):
            self.category = category
            self.questions = questions
            self.current_question_index = 0
            self.scores = {}
            self.starter = starter
            self.active = True
            self.question_start_time = None
            self.current_message = None
            self.answered_users = set()

    def calculate_points(self, response_time: float, question_type: str, difficulty: str) -> int:
        """Calculate points based on speed and difficulty"""
        base_points = {"easy": 50, "medium": 75, "hard": 100}
        max_time = 30 if question_type == "mcq" else 60
        time_bonus = max(0, int((max_time - response_time) * 2))
        return base_points.get(difficulty, 50) + time_bonus

    async def send_question_to_interaction(self, interaction: discord.Interaction, game: TriviaGame):
        """Alternative method to send questions for slash commands"""
        if game.current_question_index >= len(game.questions):
            await self.end_game_interaction(interaction, game)
            return
            
        game.answered_users.clear()
        question = game.questions[game.current_question_index]
        game.question_start_time = asyncio.get_event_loop().time()
        
        embed = discord.Embed(
            title=f"❓ Question {game.current_question_index + 1}/{len(game.questions)}",
            description=question['question'],
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Category", value=game.category.title(), inline=True)
        embed.add_field(name="Difficulty", value=question['difficulty'].title(), inline=True)
        embed.add_field(name="Time", value="30 seconds" if question['type'] == 'mcq' else "60 seconds", inline=True)
        
        if question['type'] == 'mcq':
            options_text = "\n".join([f"**{chr(65+i)}.** {option}" for i, option in enumerate(question['options'])])
            embed.add_field(name="Options", value=options_text, inline=False)
            instructions = "Type the letter of your answer (A, B, C, D)"
        else:
            instructions = "Type your answer in chat"
            
        embed.set_footer(text=instructions)
        
        try:
            if game.current_question_index == 0:
                # First question after initial response
                game.current_message = await interaction.followup.send(embed=embed)
            else:
                # Subsequent questions
                game.current_message = await interaction.channel.send(embed=embed)
        except Exception as e:
            print(f"Error sending message: {e}")
            await asyncio.sleep(1)
            game.current_message = await interaction.channel.send(embed=embed)
        
        await self.wait_for_answers_interaction(interaction, game, question)

    async def wait_for_answers_interaction(self, interaction: discord.Interaction, game: TriviaGame, question: Dict):
        """Wait for answers in interaction context"""
        timeout = 30 if question['type'] == 'mcq' else 60
        
        def check(message):
            if message.channel.id != interaction.channel.id or message.author.bot:
                return False
            if message.author.id in game.answered_users:
                return False
                
            content = message.content.strip().lower()
            
            if question['type'] == 'mcq':
                if content in ['a', 'b', 'c', 'd']:
                    answer_index = ord(content) - ord('a')
                    if answer_index < len(question['options']):
                        user_answer = question['options'][answer_index]
                        correct_answer = question['answer']
                        return user_answer.lower() == correct_answer.lower()
            else:
                correct_answer = question['answer'].lower()
                variations = [v.lower() for v in question.get('variations', [])]
                return content == correct_answer or content in variations
            
            return False

        try:
            while True:
                message = await self.bot.wait_for('message', timeout=timeout, check=check)
                
                response_time = asyncio.get_event_loop().time() - game.question_start_time
                points = self.calculate_points(response_time, question['type'], question['difficulty'])
                
                if message.author.id not in game.scores:
                    game.scores[message.author.id] = 0
                game.scores[message.author.id] += points
                game.answered_users.add(message.author.id)
                
                try:
                    await interaction.channel.send(f"✅ **{message.author.display_name}** got it right! +{points} points!", delete_after=3)
                except:
                    pass
                
                await asyncio.sleep(2)
                break
                
        except asyncio.TimeoutError:
            if question['type'] == 'mcq':
                correct_answer = question['answer']
                options = question['options']
                # Find the letter of the correct answer
                correct_letter = None
                for i, option in enumerate(options):
                    if option.lower() == correct_answer.lower():
                        correct_letter = chr(65 + i)
                        break
                if correct_letter:
                    await interaction.channel.send(f"⏰ Time's up! The correct answer was **{correct_letter}. {correct_answer}**")
                else:
                    await interaction.channel.send(f"⏰ Time's up! The correct answer was **{correct_answer}**")
            else:
                await interaction.channel.send(f"⏰ Time's up! The correct answer was **{question['answer']}**")
        
        await asyncio.sleep(2)
        game.current_question_index += 1
        await self.send_question_to_interaction(interaction, game)

    async def end_game_interaction(self, interaction: discord.Interaction, game: TriviaGame):
        """End the game for interaction context"""
        game.active = False
        
        # Update wins
        if game.scores:
            winner_id = max(game.scores.items(), key=lambda x: x[1])[0]
            self.db.add_win(interaction.guild.id, winner_id)
        
        # Show final scores
        embed = discord.Embed(
            title="🏆 Trivia Results",
            description=f"Category: **{game.category.title()}**",
            color=discord.Color.gold()
        )
        
        if game.scores:
            sorted_scores = sorted(game.scores.items(), key=lambda x: x[1], reverse=True)
            leaderboard = []
            for i, (user_id, score) in enumerate(sorted_scores[:10]):
                user = interaction.guild.get_member(user_id)
                if user:
                    medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                    leaderboard.append(f"{medal} **{user.display_name}** - {score} points")
            
            embed.add_field(name="Final Scores", value="\n".join(leaderboard), inline=False)
            
            winner_id = sorted_scores[0][0]
            winner = interaction.guild.get_member(winner_id)
            if winner:
                embed.add_field(name="Winner", value=f"🎉 **{winner.display_name}**", inline=False)
        else:
            embed.add_field(name="Results", value="No one scored any points! 😢", inline=False)
        
        await interaction.channel.send(embed=embed)
        self.active_games.pop(interaction.guild.id, None)

    async def category_autocomplete(self, interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice[str]]:
        """Autocomplete for category selection"""
        categories = self.db.get_categories()
        choices = []
        for category in categories:
            if current.lower() in category.lower():
                count = self.db.get_question_count(category)
                if count >= 7:
                    choices.append(discord.app_commands.Choice(
                        name=f"{category.title()} ({count} questions)", 
                        value=category
                    ))
        
        choices.sort(key=lambda x: x.name)
        return choices[:25]

    # SLASH COMMANDS
    @discord.app_commands.command(name="trivia", description="Start a trivia game with 7 questions")
    @discord.app_commands.describe(category="Choose a category for the trivia")
    @discord.app_commands.autocomplete(category=category_autocomplete)
    async def trivia_slash(self, interaction: discord.Interaction, category: str):
        """Slash command to start trivia"""
        if interaction.guild.id in self.active_games:
            await interaction.response.send_message("❌ A trivia game is already running in this server!", ephemeral=True)
            return
        
        # Get available categories
        available_categories = self.db.get_categories()
        if not available_categories:
            await interaction.response.send_message(
                "❌ No categories available! The database might be empty. Please contact an administrator.", 
                ephemeral=True
            )
            return
            
        if category.lower() not in [c.lower() for c in available_categories]:
            await interaction.response.send_message(
                f"❌ Category not found! Available categories: {', '.join([c.title() for c in available_categories])}", 
                ephemeral=True
            )
            return
        
        # Find the exact category name from database
        exact_category = None
        for cat in available_categories:
            if cat.lower() == category.lower():
                exact_category = cat
                break
        
        if not exact_category:
            await interaction.response.send_message("❌ Category not found!", ephemeral=True)
            return
        
        questions = self.db.get_questions(exact_category, 7)
        if len(questions) < 7:
            await interaction.response.send_message(
                f"❌ Not enough questions in this category! Need 7, but only {len(questions)} available.", 
                ephemeral=True
            )
            return
        
        game = self.TriviaGame(exact_category, questions, interaction.user)
        self.active_games[interaction.guild.id] = game
        
        embed = discord.Embed(
            title="🎯 Trivia Game Starting!",
            description=f"Started by: {interaction.user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Category", value=exact_category.title(), inline=True)
        embed.add_field(name="Questions", value="7", inline=True)
        embed.add_field(name="Format", value="Mixed (MCQ & Text)", inline=True)
        embed.add_field(
            name="How to Play", 
            value="• Answer quickly for more points!\n• First correct answer moves to next question\n• MCQ: 30s, Text: 60s", 
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(3)
        
        # Use the interaction-specific method
        await self.send_question_to_interaction(interaction, game)

    @discord.app_commands.command(name="trivia_stop", description="Stop the current trivia game (Admin only)")
    async def trivia_stop_slash(self, interaction: discord.Interaction):
        """Stop current trivia game"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to stop trivia!", ephemeral=True)
            return
            
        if interaction.guild.id not in self.active_games:
            await interaction.response.send_message("❌ No active trivia game in this server!", ephemeral=True)
            return
        
        game = self.active_games[interaction.guild.id]
        game.active = False
        self.active_games.pop(interaction.guild.id, None)
        await interaction.response.send_message("🛑 Trivia game stopped by admin!")

    @discord.app_commands.command(name="trivia_leaderboard", description="Show trivia wins leaderboard")
    async def trivia_leaderboard_slash(self, interaction: discord.Interaction):
        """Show wins leaderboard"""
        wins_data = self.db.get_wins(interaction.guild.id)
        
        if not wins_data:
            await interaction.response.send_message("No trivia wins recorded yet! Start a game with `/trivia`")
            return
        
        embed = discord.Embed(title="🏆 Trivia Wins Leaderboard", color=discord.Color.purple())
        
        leaderboard = []
        for i, win_data in enumerate(wins_data):
            user = interaction.guild.get_member(win_data['user_id'])
            if user:
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
                wins = win_data['wins']
                leaderboard.append(f"{medal} **{user.display_name}** - {wins} win{'s' if wins > 1 else ''}")
        
        embed.description = "\n".join(leaderboard) if leaderboard else "No wins yet!"
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="trivia_categories", description="Show available trivia categories")
    async def trivia_categories_slash(self, interaction: discord.Interaction):
        """Show available categories"""
        categories = self.db.get_categories()
        
        if not categories:
            await interaction.response.send_message("No categories available yet! The database might be empty.")
            return
        
        embed = discord.Embed(title="📚 Trivia Categories", color=discord.Color.blue())
        
        for category in categories:
            count = self.db.get_question_count(category)
            status = "✅" if count >= 7 else "⚠️"
            embed.add_field(
                name=f"{status} {category.title()}",
                value=f"{count} questions",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed)

    # QUESTION MANAGEMENT COMMANDS
    @discord.app_commands.command(name="add_question", description="Add a new trivia question (Admin only)")
    @discord.app_commands.describe(
        category="Category for the question",
        question="The question text",
        q_type="Type of question",
        answer="The correct answer",
        difficulty="Question difficulty",
        option1="Option A (for MCQ)",
        option2="Option B (for MCQ)", 
        option3="Option C (for MCQ)",
        option4="Option D (for MCQ)",
        variations="Comma-separated answer variations (for text questions)"
    )
    @discord.app_commands.choices(
        q_type=[
            discord.app_commands.Choice(name="Multiple Choice", value="mcq"),
            discord.app_commands.Choice(name="Text Answer", value="text")
        ],
        difficulty=[
            discord.app_commands.Choice(name="Easy", value="easy"),
            discord.app_commands.Choice(name="Medium", value="medium"), 
            discord.app_commands.Choice(name="Hard", value="hard")
        ]
    )
    async def add_question_slash(self, interaction: discord.Interaction, 
                               category: str, question: str, q_type: discord.app_commands.Choice[str],
                               answer: str, difficulty: discord.app_commands.Choice[str],
                               option1: str = None, option2: str = None, option3: str = None, 
                               option4: str = None, variations: str = None):
        """Add a new question to the database"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to add questions!", ephemeral=True)
            return
        
        # Validate MCQ options
        options = []
        if q_type.value == 'mcq':
            options = [opt for opt in [option1, option2, option3, option4] if opt is not None]
            if len(options) < 2:
                await interaction.response.send_message("❌ MCQ questions need at least 2 options!", ephemeral=True)
                return
            if answer not in options:
                await interaction.response.send_message("❌ Answer must match one of the options!", ephemeral=True)
                return
        
        # Parse variations
        variation_list = [v.strip() for v in variations.split(',')] if variations else None
        
        success = self.db.add_question(
            category=category.lower(),
            question=question,
            q_type=q_type.value,
            answer=answer,
            difficulty=difficulty.value,
            added_by=interaction.user.id,
            options=options if q_type.value == 'mcq' else None,
            variations=variation_list if q_type.value == 'text' else None
        )
        
        if success:
            await interaction.response.send_message(f"✅ Question added to **{category}** category!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to add question. Please check the format.", ephemeral=True)

    @discord.app_commands.command(name="delete_question", description="Delete a trivia question (Admin only)")
    @discord.app_commands.describe(question_id="ID of the question to delete")
    async def delete_question_slash(self, interaction: discord.Interaction, question_id: int):
        """Delete a question by ID"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to delete questions!", ephemeral=True)
            return
        
        success = self.db.delete_question(question_id)
        if success:
            await interaction.response.send_message("✅ Question deleted successfully!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Question not found or couldn't be deleted!", ephemeral=True)

    @discord.app_commands.command(name="search_questions", description="Search for questions")
    @discord.app_commands.describe(query="Search term", category="Filter by category (optional)")
    async def search_questions_slash(self, interaction: discord.Interaction, query: str, category: str = None):
        """Search questions in the database"""
        questions = self.db.search_questions(query, category)
        
        if not questions:
            await interaction.response.send_message("No questions found matching your search!", ephemeral=True)
            return
        
        embed = discord.Embed(title="🔍 Search Results", color=discord.Color.orange())
        
        for i, q in enumerate(questions[:5]):
            q_text = q['question'][:100] + "..." if len(q['question']) > 100 else q['question']
            embed.add_field(
                name=f"ID: {q['id']} | {q['category'].title()}",
                value=f"{q_text}\n**Answer:** ||{q['answer']}||",
                inline=False
            )
        
        if len(questions) > 5:
            embed.set_footer(text=f"Showing 5 of {len(questions)} results")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="question_stats", description="Show question statistics")
    async def question_stats_slash(self, interaction: discord.Interaction):
        """Show database statistics"""
        total_questions = self.db.get_question_count()
        categories = self.db.get_categories()
        
        embed = discord.Embed(title="📊 Question Statistics", color=discord.Color.green())
        embed.add_field(name="Total Questions", value=total_questions, inline=True)
        embed.add_field(name="Categories", value=len(categories), inline=True)
        
        category_stats = ""
        for category in categories:
            count = self.db.get_question_count(category)
            category_stats += f"**{category.title()}**: {count}\n"
            
        embed.add_field(name="Questions per Category", value=category_stats, inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Trivia(bot))
import json  
import ollama
from datetime import datetime, timedelta
from collections import defaultdict
import os
import streamlit as st
import time
from typing import Dict, Generator
import requests
import discord
from discord.ext import commands
from dotenv import load_dotenv
import re
from llm_axe import OnlineAgent, OllamaChat
import itertools
import threading
import sys

user_prompt = "You: "  
assistant_name = "Aurora"  
model_name = "test"  
chat_messages = []
llm = OllamaChat(model="test")
agent = OnlineAgent(llm)
initial_message_processed = False


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

chat_messages = []

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user.name}")

    global chat_messages
    chat_messages = load_chat_history("chat_history.json")

def spinning_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor

spinner = spinning_cursor()

def save_chat_history(filename):
    global chat_messages

    with open(filename, 'w') as f:
        json.dump(chat_messages, f, indent=2)

def load_chat_history(filename):
    try:
        with open(filename, 'r') as f:
            messages = json.load(f)  

            for message in messages:
                if 'timestamp' not in message:
                    message['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return messages
    except FileNotFoundError:
        return []  

def create_message(message, role):
    return {
        'role': role,
        'content': message,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")  
    }

def summarize_messages(messages):

    summary = messages[0]['content'] if messages else ""

    for i in range(1, len(messages)):

        summary += f"\n{messages[i]['role']}: {messages[i]['content']}"

    return summary

def ask(user_message):
    global initial_message_processed
    full_message = f"{user_message}"
    chat_messages.append(create_message(full_message, 'user'))
    
    # Set the flag to indicate the initial message has been processed
    initial_message_processed = True
    
    # Now, call the chat function to get the assistant's response
    chat()


def chat():
    ollama_response = ollama.chat(model=model_name, stream=True, messages=chat_messages)

    global assistant_message
    assistant_message = ''
    for chunk in ollama_response:
        assistant_message += chunk['message']['content']
    
    # Only proceed with search and formatting if the initial message has been processed
    if initial_message_processed:
        create_file_from_ai_response(assistant_message)
        edit_file_from_ai_response(assistant_message)
        extract_search_query(assistant_message)
    
    chat_messages.append(create_message(assistant_message, 'assistant'))
    print(f"\n{assistant_name}: {assistant_message}\n")


def main():
    print("Which version would you like to run?")
    print("1. Discord bot")
    print("2. Console chat")
    choice = input("Enter your choice (1 or 2): ")

    if choice == "1":
        bot.run(TOKEN)
    elif choice == "2":
        while True:
            user_message = input(user_prompt)

            if user_message.lower() == "exit":
                break
            else:
                ask(user_message)

            save_chat_history("chat_history.json")
    else:
        print("Invalid choice. Please enter 1 or 2.")

import re

def create_file_from_ai_response(response: str):

    matches = re.findall(r'\$&(.+?)\$&', response)

    for match in matches:

        requested_path = match.strip()
        requested_directory, file_name = requested_path.rsplit(' ', 1)

        os.makedirs(requested_directory, exist_ok=True)

        with open(os.path.join(requested_directory, file_name), 'w') as f:
            f.write('')  

        print(f"File '{file_name}' created at '{requested_directory}'")

def edit_file_from_ai_response(response: str):

    matches = re.findall(r'\$@(.+?)\$@', response)

    for match in matches:

        dir_end_index = match.find(' ', match.find(':\\') + 2)

        file_path = match[:dir_end_index].strip()
        new_contents = match[dir_end_index:].strip()

        if os.path.isfile(file_path):

            with open(file_path, 'w') as f:
                f.write(new_contents)

            print(f"Contents of file '{file_path}' updated")
        else:
            print(f"File '{file_path}' not found")

import json

import requests  

def extract_search_query(original_message):
    match = re.search(r'\$\$(.+?)\$\$', original_message)

    if match:
        query = match.group(1)
        print(f"Searching for: {query}")

        # Start the spinner in a separate thread
        spinner_thread = threading.Thread(target=spin, daemon=True)
        spinner_thread.start()

        try:
            result = agent.search(query)
            print(result)
            # Stop the spinner
            global stop_spinner
            stop_spinner = True
            spinner_thread.join()
            
            # Format the search results
            formatted_results = "\n".join([f"- {item}" for item in result])
            # Construct the final message with the assistant's response and search results
            final_message = f"Aurora: {original_message}\n\nBased on information from the internet, {formatted_results}"
            return final_message
        except requests.exceptions.MissingSchema:
            print("Error: Something involving the URL broke, please try again.")
            stop_spinner = True
            spinner_thread.join()
            return original_message
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            stop_spinner = True
            spinner_thread.join()
            return original_message
    else:
        return original_message




# Function to spin the cursor
def spin():
    global stop_spinner
    stop_spinner = False
    for _ in spinner:
        if stop_spinner:
            break
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        time.sleep(0.1)
        sys.stdout.write('\b')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        chat_messages.append({'role': 'user', 'content': message.content})
        response = ollama.chat(model=model_name, messages=chat_messages)
        
        # Send a temporary loading message
        temp_msg = await message.channel.send("Searching... Please wait.")
        
        # Extract search query and concatenate results with the original message
        combined_message = extract_search_query(response['message']['content'])
        
        # Edit the temporary message with the actual response
        await temp_msg.edit(content=combined_message)

        create_file_from_ai_response(combined_message)
        edit_file_from_ai_response(combined_message)

        save_chat_history("chat_history.json")

if __name__ == "__main__":
    main()

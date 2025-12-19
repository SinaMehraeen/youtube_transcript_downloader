import os
import re
import csv
from pathlib import Path
from collections import defaultdict

def count_words_after_separator(file_path):
    """
    Count words in markdown file after the separator line.
    Returns 0 if separator not found or file cannot be read.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the separator (40 equal signs)
        separator = '=' * 40
        
        # Split by separator and take content after it
        parts = content.split(separator)
        if len(parts) < 2:
            return 0  # No separator found
        
        # Get content after the separator
        content_after = parts[1]
        
        # Count words (split by whitespace)
        words = content_after.split()
        return len(words)
    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0

def calculate_reading_time(word_count, words_per_minute=250):
    """Calculate reading time in minutes."""
    return word_count / words_per_minute

def categorize_by_reading_time(folders):
    """
    Analyze markdown files in given folders and categorize by reading time.
    
    Args:
        folders: List of folder paths to analyze
    
    Returns:
        Dictionary with categories and file counts
    """
    categories = {
        'less_than_2': 0,
        '2_to_5': 0,
        '5_to_10': 0,
        '10_to_15': 0,
        'more_than_15': 0
    }
    
    files_by_category = defaultdict(list)
    
    for folder in folders:
        folder_path = Path(folder)
        
        if not folder_path.exists():
            print(f"Warning: Folder '{folder}' does not exist")
            continue
        
        # Find all markdown files recursively
        md_files = list(folder_path.rglob('*.md'))
        
        for md_file in md_files:
            word_count = count_words_after_separator(md_file)
            
            if word_count == 0:
                continue  # Skip files with no content after separator
            
            reading_time = calculate_reading_time(word_count)
            
            # Categorize
            if reading_time < 2:
                categories['less_than_2'] += 1
                files_by_category['less_than_2'].append((md_file, reading_time, word_count))
            elif reading_time < 5:
                categories['2_to_5'] += 1
                files_by_category['2_to_5'].append((md_file, reading_time, word_count))
            elif reading_time < 10:
                categories['5_to_10'] += 1
                files_by_category['5_to_10'].append((md_file, reading_time, word_count))
            elif reading_time < 15:
                categories['10_to_15'] += 1
                files_by_category['10_to_15'].append((md_file, reading_time, word_count))
            else:
                categories['more_than_15'] += 1
                files_by_category['more_than_15'].append((md_file, reading_time, word_count))
    
    return categories, files_by_category

def save_to_csv(files_by_category, base_path, output_file='reading_time_analysis.csv'):
    """Save detailed file information to CSV with relative paths."""
    base_path = Path(base_path)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['File Name', 'Relative Path', 'Word Count', 'Reading Time (minutes)', 'Category'])
        
        category_labels = {
            'less_than_2': 'Less than 2 minutes',
            '2_to_5': '2-5 minutes',
            '5_to_10': '5-10 minutes',
            '10_to_15': '10-15 minutes',
            'more_than_15': 'More than 15 minutes'
        }
        
        for category in ['less_than_2', '2_to_5', '5_to_10', '10_to_15', 'more_than_15']:
            for file_path, reading_time, word_count in files_by_category[category]:
                try:
                    # Get relative path from base path
                    relative_path = file_path.relative_to(base_path)
                except ValueError:
                    # If file is not relative to base_path, just use the name
                    relative_path = file_path.name
                
                writer.writerow([
                    file_path.name,
                    str(relative_path),
                    word_count,
                    f"{reading_time:.2f}",
                    category_labels[category]
                ])

def main():
    # Define the base path (parent of all folders to analyze)
    base_path = r'C:\Users\admina\Desktop\Projects\Youtube_Transcript_Downloader-main\cleaned'
    
    # Define the three folders to analyze
    folders = [
        r'C:\Users\admina\Desktop\Projects\Youtube_Transcript_Downloader-main\cleaned\OxfordSparks',
        r'C:\Users\admina\Desktop\Projects\Youtube_Transcript_Downloader-main\cleaned\Sprouts',
        r'C:\Users\admina\Desktop\Projects\Youtube_Transcript_Downloader-main\cleaned\TED_ED'
    ]
    
    print("Analyzing markdown files...")
    print(f"Reading speed: 250 words per minute\n")
    
    categories, files_by_category = categorize_by_reading_time(folders)
    
    # Print only the counts
    print("=" * 50)
    print("READING TIME ANALYSIS")
    print("=" * 50)
    print(f"1. Files requiring less than 2 minutes:  {categories['less_than_2']}")
    print(f"2. Files requiring 2-5 minutes:          {categories['2_to_5']}")
    print(f"3. Files requiring 5-10 minutes:         {categories['5_to_10']}")
    print(f"4. Files requiring 10-15 minutes:        {categories['10_to_15']}")
    print(f"5. Files requiring more than 15 minutes: {categories['more_than_15']}")
    print("=" * 50)
    
    total = sum(categories.values())
    print(f"Total files analyzed: {total}")
    
    # Save detailed information to CSV with relative paths
    csv_filename = 'reading_time_analysis.csv'
    save_to_csv(files_by_category, base_path, csv_filename)
    print(f"\nDetailed file information saved to: {csv_filename}")

if __name__ == "__main__":
    main()
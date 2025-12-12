import json

def format_prompt(user_message, project_data):
    """
    Combines user message + project-specific data into one prompt
    that will be sent to Hugging Face.
    """
    project_name = project_data.get("project", "This Project")
    data_str = json.dumps(project_data, indent=2)

    prompt = f"""
You are an intelligent assistant for the project: {project_name}.

Here is the project's data:
{data_str}

User Question:
{user_message}

Based ONLY on the above data, give the best possible answer.
If the data does not contain the answer, say: 'I don't have that information.'
"""
    return prompt
